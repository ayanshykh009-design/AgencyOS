"""M10 docs/API consistency: ensure endpoint docs don't claim phantom routes.

Compares the routes exposed by the FastAPI app against the paths referenced in
``docs/api/endpoints/*.md``.

Exit codes:
  * 0 -> no documentation drift (every path referenced in the docs actually
         exists in the backend). Routes that exist but are not yet documented
         are reported as a coverage metric only.
  * 1 -> a doc file references a backend route that does not exist (genuine
         documentation inconsistency that must be fixed).

Run from the repo root or backend dir:
    python scripts/ci/docs_api_consistency.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DOCS_DIR = REPO_ROOT / "docs" / "api" / "endpoints"

PATH_RE = re.compile(r"/api/v1/[A-Za-z0-9_/{}/.:$-]+")


def load_backend_paths() -> set[str]:
    sys.path.insert(0, str(BACKEND_DIR))
    from app.main import app  # noqa: E402

    paths = set()
    for raw in app.openapi().get("paths", {}).keys():
        paths.add(raw.rstrip("/"))
    return paths


def load_documented_paths() -> tuple[set[str], list[str]]:
    documented: set[str] = set()
    files: list[str] = []
    if not DOCS_DIR.exists():
        return documented, files
    for md in DOCS_DIR.glob("*.md"):
        files.append(md.name)
        text = md.read_text(encoding="utf-8")
        for m in PATH_RE.finditer(text):
            p = m.group(0).rstrip("/")
            # Drop obvious non-route tokens (markdown table separators etc.).
            if p.count("/") < 3:
                continue
            documented.add(p)
    return documented, files


def main() -> int:
    backend = load_backend_paths()
    documented, files = load_documented_paths()

    drift = sorted(p for p in documented if p not in backend)
    uncovered = sorted(p for p in backend if p not in documented)

    report = {
        "backend_routes": len(backend),
        "doc_files": len(files),
        "documented_paths": len(documented),
        "drift": drift,
        "undocumented_routes": uncovered,
    }
    out = REPO_ROOT / "storage" / "m10-docs-consistency.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Backend routes: {len(backend)}")
    print(f"Doc files: {len(files)}  Documented paths: {len(documented)}")
    print(f"Documentation coverage: {len(documented & backend)}/{len(backend)} backend routes")
    if drift:
        print("DRIFT (docs reference routes not in backend — must fix):")
        for d in drift:
            print("  - " + d)
    if uncovered:
        print(f"WARNING: {len(uncovered)} backend routes are not referenced in endpoint docs.")
    print(f"Report written to {out}")

    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
