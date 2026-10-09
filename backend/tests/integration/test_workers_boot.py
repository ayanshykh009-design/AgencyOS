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
START_WORKERS = (
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "prod" / "start_workers.sh"
)


def _shutdown_handler_body(text: str) -> str:
    """Return the body of the ``shutdown()`` function (braces may not nest)."""
    start = text.find("shutdown() {")
    if start == -1:
        return ""
    end = text.find("\n}", start)
    return text[start:end] if end != -1 else text[start:]


def test_start_workers_sigterm_traps_and_forwards_to_child_pids() -> None:
    """Regression: the SIGTERM trap must signal the tracked child PIDs.

    The previous handler did ``kill -TERM "$@"`` — inside a trap ``$@`` is the
    *script's* arguments (none under docker), so children were never signalled
    and `docker stop` degraded to SIGKILL without a drain window.
    """
    text = START_WORKERS.read_text(encoding="utf-8")
    assert "trap shutdown TERM INT" in text, "the script must trap TERM/INT"
    code = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    assert '"$@"' not in code, '"$@" in a trap is the script args, not the children'
    body = _shutdown_handler_body(code)
    assert body, "shutdown() handler missing"
    assert "kill -TERM ${PIDS:-}" in body, "handler must signal tracked child PIDs"
    assert "wait" in body, "handler must wait for children to drain"
START_WORKERS = (
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "prod" / "start_workers.sh"
)


def test_start_workers_sigterm_trap_forwards_to_children():
    """Regression: the shutdown trap must signal the tracked child PIDs.

    ``"$@"`` inside a trap expands to the *script's* arguments (docker
    invokes it with none), so the previous handler never reached the worker
    processes and `docker stop` degraded to a SIGKILL. Children must be
    signalled by their recorded PIDs and re-waited for a clean drain.
    """
    text = START_WORKERS.read_text(encoding="utf-8")
    trap_lines = [ln for ln in text.splitlines() if ln.strip().startswith("trap ")]
    assert trap_lines, "start_workers.sh must trap TERM/INT"
    trap_block = "\n".join(trap_lines)
    assert "shutdown" in trap_block
    assert '"$@"' not in trap_block, '"$@" in a trap is the script args, not the children'
    # The handler must signal the recorded PIDs (defended against set -u).
    assert "kill -TERM ${PIDS:-}" in text or "kill -TERM $PIDS" in text
    assert "wait" in text, "handler must re-wait children for a clean drain"


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
