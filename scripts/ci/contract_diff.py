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
            # A template variable inside a path segment. If the entire segment
            # is the variable it is a path parameter; otherwise it is a suffix
            # appended to a static segment (commonly a query string such as
            # `close-reasons${qs}`) and the variable part must be dropped so the
            # static path segment remains comparable to the backend route.
            prefix = p.split("${", 1)[0]
            p = "*" if prefix == "" else prefix
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


# Typed call with explicit method: apiFetch<T>('/path', { method: 'POST' })
_CALL_RE = re.compile(
    r"""apiFetch\s*<\s*[^>]*>\s*\(\s*["'`]([^"'`]+)["'`]\s*,\s*\{[^}]*?method\s*:\s*["']?([A-Za-z]+)["']?""",
    re.DOTALL,
)
# Simple call (defaults to GET) or with method supplied later.
_SIMPLE_RE = re.compile(r"""apiFetch\s*<\s*[^>]*>\s*\(\s*["'`]([^"'`]+)["'`]""")

# File-local `const NAME = "literal"` string constants (e.g. API_BASE).
_CONST_RE = re.compile(r"""\bconst\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*["']([^"']*)["']""")


def collect_constants(text: str) -> dict[str, str]:
    """Extract file-local ``const NAME = "literal"`` string constants."""
    return {m.group(1): m.group(2) for m in _CONST_RE.finditer(text)}


def expand_constants(path: str, consts: dict[str, str]) -> str:
    """Resolve ``${NAME}`` references to their literal constant values."""
    prev = None
    cur = path
    for _ in range(4):  # bounded iteration handles chained constants
        if cur == prev:
            break
        prev = cur
        cur = re.sub(
            r"""\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}""",
            lambda m: consts.get(m.group(1), m.group(0)),
            cur,
        )
    return cur


def extract_calls_from_text(text: str) -> dict[str, set[str]]:
    """Return normalized frontend calls parsed from a single TS source file."""
    calls: dict[str, set[str]] = {}
    consts = collect_constants(text)
    for m in _CALL_RE.finditer(text):
        raw = expand_constants(m.group(1), consts)
        calls.setdefault(normalize(raw), set()).add(m.group(2).upper())
    for m in _SIMPLE_RE.finditer(text):
        raw = expand_constants(m.group(1), consts)
        norm = normalize(raw)
        window = text[max(0, m.start() - 200):m.start()]
        if re.search(r"""method\s*:\s*[`'"]""", window):
            continue
        # Only default to GET when no explicit method was captured for this
        # path (avoids a spurious GET alongside a real POST/PUT/PATCH).
        if norm in calls:
            continue
        calls.setdefault(norm, set()).add("GET")
    return calls


def frontend_calls() -> dict[str, set[str]]:
    """Map normalized path -> set of HTTP methods the frontend calls."""
    calls: dict[str, set[str]] = {}
    for f in FRONTEND_SERVICES.rglob("*.ts"):
        if f.name.endswith(".test.ts"):
            continue
        for path, methods in extract_calls_from_text(f.read_text(encoding="utf-8")).items():
            calls.setdefault(path, set()).update(methods)
    return calls


def analyze(
    calls: dict[str, set[str]], routes: dict[str, set[str]]
) -> tuple[list[str], list[str], list[str]]:
    """Compare frontend calls against backend routes.

    Returns ``(drift, method_warnings, uncovered_backend_routes)``.
    """
    backend_keys = set(routes.keys())
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
    covered = set(calls.keys())
    uncovered = sorted(
        k for k in backend_keys if k not in covered and not any(a in k for a in INTERNAL_ALLOW)
    )
    return drift, method_warnings, uncovered


def main() -> int:
    openapi = load_openapi()
    routes = backend_routes(openapi)
    calls = frontend_calls()

    drift, method_warnings, uncovered = analyze(calls, routes)

    report = {
        "backend_routes": len(routes),
        "frontend_call_sites": sum(len(v) for v in calls.values()),
        "frontend_unique_calls": sum(len(v) for v in calls.values()),
        "drift": drift,
        "method_warnings": method_warnings,
        "uncovered_backend_routes": uncovered,
    }
    out = REPO_ROOT / "storage" / "m10-contract-diff.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Backend routes: {len(routes)}")
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
