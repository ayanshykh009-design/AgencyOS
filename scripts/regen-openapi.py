"""Regenerate docs/api/openapi.yaml from the live ASGI app.

Run from repo root (or with PYTHONPATH including backend):
    python scripts/regen-openapi.py

This is the documented workflow in docs/api/README.md: the OpenAPI JSON is
served live; the pinned YAML is a committed snapshot refreshed after any
endpoint/schema change.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402

OUT = ROOT / "docs" / "api" / "openapi.yaml"


def main() -> None:
    spec = app.openapi()
    text = yaml.safe_dump(spec, sort_keys=False, default_flow_style=False, width=120)
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    main()
