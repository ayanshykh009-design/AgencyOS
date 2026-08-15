"""M10 worker boot readiness (no database required).

Every production worker launched by ``scripts/prod/start_workers.sh`` must be
importable and expose a ``_worker_entrypoint()`` that ``python -m
app.workers.<name>`` invokes. Importing the module must not connect to any
backend (Postgres/Redis) at import time, so a broken import surfaces here
without needing the full runtime.

In-process job processors (import/research) have no ``__main__`` guard; they
expose ``process_job`` and are driven by the API layer, so they are verified
for importability + their entry method instead.
"""

from __future__ import annotations

import importlib
import pathlib

import pytest

WORKERS_DIR = pathlib.Path(__file__).resolve().parents[2] / "app" / "workers"


def _worker_modules():
    return sorted(WORKERS_DIR.glob("*_worker.py"))


def _has_main_guard(path: pathlib.Path) -> bool:
    return 'if __name__ == "__main__":' in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("module_path", _worker_modules(), ids=lambda p: p.stem)
def test_worker_module_imports(module_path):
    module = importlib.import_module(f"app.workers.{module_path.stem}")
    assert module is not None


@pytest.mark.parametrize("module_path", _worker_modules(), ids=lambda p: p.stem)
def test_launchable_worker_has_entrypoint(module_path):
    module = importlib.import_module(f"app.workers.{module_path.stem}")
    if _has_main_guard(module_path):
        # Standalone process worker: must expose a callable entrypoint.
        assert hasattr(module, "_worker_entrypoint"), (
            f"{module_path.stem} has a __main__ guard but no _worker_entrypoint()"
        )
        assert callable(module._worker_entrypoint)
    else:
        # In-process job processor: a class exposing process_job() is driven
        # by the API layer (not launched as a standalone process).
        has_processor = any(
            isinstance(v, type) and hasattr(v, "process_job")
            for v in vars(module).values()
        )
        assert has_processor, (
            f"{module_path.stem} has no __main__ guard and no job processor class"
        )
