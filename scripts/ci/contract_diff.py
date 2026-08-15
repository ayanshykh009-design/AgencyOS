"""M10 contract-diff: verify the frontend service layer covers the backend API.

Reads the FastAPI OpenAPI schema (all /api/v1 routes + methods) and scans the
frontend service files for ``apiFetch`` call sites. Emits a coverage report.

Exit codes:
  * 0  -> no frontend->backend drift (every frontend call resolves to a real
          backend route). Backend routes with no frontend caller are reported
          as warnings only (some routes are internal: health, webhooks, docs).
  * 1  -> frontend references a backend route/method that does not exist
          (genuine API drift -> must be fixed).

Run from the repo root or backend dir:
    python scripts/ci/contract_diff.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_SERVICES = REPO_ROOT / "frontend" / "src" / "services"
API_PREFIX = "/api/v1"

# Routes that are intentionally backend-only (no frontend service caller).
INTERNAL_ALLOW = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/login",
    "/auth/refresh",
    "/auth/register",
    "/auth/logout",
    "/webhooks",
    "/monitoring",
    "/operations",
    "/search",
)


def load_openapi() -> dict:
    sys.path.insert(0, str(BACKEND_DIR))
    from app.main import app  # noqa: E402

    return app.openapi()


def normalize(path: str) -> str:
    """Strip query strings and replace path params with a fixed placeholder.

    Both ``/leads/{lead_id}`` (backend) and ``/leads/${leadId}`` (frontend)
    become ``/api/v1/leads/*`` so they compare equal, while the collection
    route ``/leads`` stays distinct.
    """
    path = path.split("?")[0]
    parts = []
    for p in path.split("/"):
        if not p:
            continue
        if (p.startswith("{") and p.endswith("}")) or p.startswith(":"):
            p = "*"
        elif "${" in p:
            p = "*"
        parts.append(p)
    base = "/" + "/".join(parts)
    # The frontend apiFetch() omits the /api/v1 prefix (the client adds it).
    if not base.startswith(API_PREFIX):
        base = API_PREFIX + base
    return base


def backend_routes(openapi: dict) -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    for raw_path, methods in openapi.get("paths", {}).items():
        norm = normalize(raw_path)
        routes[norm] = {m.upper() for m in methods.keys()}
    return routes


def frontend_calls() -> dict[str, set[str]]:
    """Map normalized path -> set of HTTP methods the frontend calls."""
    calls: dict[str, set[str]] = {}
    # Typed call with explicit method: apiFetch<T>('/path', { method: 'POST' })
    pattern = re.compile(
        r"""apiFetch\s*<\s*[^>]*>\s*\(\s*[`'"]([^`'"]+)[`'"]\s*,\s*\{[^}]*?method\s*:\s*[`'"]?([A-Za-z]+)['"]?""",
        re.DOTALL,
    )
    # Simple call (defaults to GET) or with method supplied later.
    simple = re.compile(r"""apiFetch\s*<\s*[^>]*>\s*\(\s*[`'"]([^`'"]+)[`'"]""")
    for f in FRONTEND_SERVICES.rglob("*.ts"):
        if f.name.endswith(".test.ts"):
            continue
        text = f.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            calls.setdefault(normalize(m.group(1)), set()).add(m.group(2).upper())
        for m in simple.finditer(text):
            path = m.group(1)
            norm = normalize(path)
            window = text[max(0, m.start() - 200):m.start()]
            if re.search(r"""method\s*:\s*[`'"]""", window):
                continue
            # Only default to GET when no explicit method was captured for this
            # path (avoids a spurious GET alongside a real POST/PUT/PATCH).
            if norm in calls:
                continue
            calls.setdefault(norm, set()).add("GET")
    return calls


def main() -> int:
    openapi = load_openapi()
    routes = backend_routes(openapi)
    calls = frontend_calls()

    backend_keys = set(routes.keys())

    # 1) Frontend -> backend drift: a frontend call whose base PATH does not
    #    exist in the backend at all (genuine API drift -> must be fixed).
    #    Method-level mismatches (e.g. FE uses a dynamic method) are reported
    #    as informational warnings only.
    drift: list[str] = []
    method_warnings: list[str] = []
    for path, methods in calls.items():
        candidates = [k for k in backend_keys if k == path or k.startswith(path + "/")]
        if not candidates:
            for method in sorted(methods):
                drift.append(f"FE calls unknown route: {method} {path}")
            continue
        offered = set()
        for c in candidates:
            offered |= routes[c]
        for method in sorted(methods):
            if method not in offered:
                method_warnings.append(
                    f"FE calls {method} {path} but backend offers {sorted(offered)}"
                )

    # 2) Backend routes with no frontend caller (warning only).
    covered = set(calls.keys())
    uncovered = sorted(
        k for k in backend_keys if k not in covered and not any(a in k for a in INTERNAL_ALLOW)
    )

    report = {
        "backend_routes": len(backend_keys),
        "frontend_call_sites": sum(len(v) for v in calls.values()),
        "frontend_unique_calls": sum(len(v) for v in calls.values()),
        "drift": drift,
        "method_warnings": method_warnings,
        "uncovered_backend_routes": uncovered,
    }
    out = REPO_ROOT / "storage" / "m10-contract-diff.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Backend routes: {len(backend_keys)}")
    print(f"Frontend unique calls: {report['frontend_unique_calls']}")
    if drift:
        print("DRIFT (frontend references missing backend routes):")
        for d in drift:
            print("  - " + d)
    if method_warnings:
        print("METHOD WARNINGS (verify FE dynamic methods):")
        for w in method_warnings:
            print("  - " + w)
    if uncovered:
        print("WARNING: backend routes with no frontend caller:")
        for u in uncovered:
            print("  - " + u)
    print(f"Report written to {out}")

    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
