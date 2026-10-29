"""Repository-wide guard for SlowAPI's ``response`` header-injection contract.

``Limiter(headers_enabled=True)`` appends ``X-RateLimit-*``/``Retry-After``
headers to the ``response`` argument of every limited handler. When a handler
decorated with ``@limiter.limit(...)`` does not declare ``response: Response``,
slowapi raises *after* the handler succeeded::

    parameter `response` must be an instance of starlette.responses.Response

which surfaces to clients as an HTTP 500 on the success path. This module scans
every endpoint module in the project and fails if any limited handler is missing
the parameter, so the regression cannot return silently in a new router.

The scanner is deliberately source-only (``ast``) rather than import-based: it
covers every endpoint file without booting the app, and it can be exercised
against a synthetic snippet missing the parameter (see the self-tests) without
temporarily breaking production code.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ENDPOINTS_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints"
)
# slowapi's header-injecting decorators. Matched on the attribute name so
# aliased imports (``rl.limit``) are covered too. ``limiter.exempt`` is excluded
# because it removes the limit and never injects headers.
LIMITER_DECORATORS = frozenset({"limit", "shared_limit"})
# Baseline inventory at the time of the R7 fix: 13 auth routes, 5 AI routes,
# 2 agent routes, 2 team routes. Guarding the count keeps a broken scanner
# (which would trivially report "no offenders") from passing.
MIN_LIMITED_HANDLERS = 22


def _call_attr(node: ast.expr) -> str | None:
    """Return the attribute name of a ``name.attr(...)`` call, if any."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _limiter_aliases(tree: ast.Module) -> set[str]:
    """Module-level aliases for a limiter decorator (``strict = limiter.limit``)."""
    aliases: set[str] = set()
    for node in tree.body:
        value = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is not None and _call_attr(value) in LIMITER_DECORATORS:
            aliases.update(t.id for t in targets if isinstance(t, ast.Name))
    return aliases


def _is_limiter_decorator(node: ast.expr, aliases: set[str]) -> bool:
    if _call_attr(node) in LIMITER_DECORATORS:
        return True
    return isinstance(node, ast.Name) and node.id in aliases


def _arg_names(handler: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = handler.args
    return {
        arg.arg
        for arg in (
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
            *([args.vararg] if args.vararg else []),
            *([args.kwarg] if args.kwarg else []),
        )
    }


def _response_param(handler: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.arg | None:
    args = handler.args
    for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
        if arg.arg == "response":
            return arg
    return None


def _annotation_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.rsplit(".", 1)[-1]
    return None


def scan_limited_handlers(source: str) -> tuple[list[str], list[str]]:
    """Return ``(offenders, inventory)`` for one module source.

    ``offenders`` are readable ``file:line function (reason)`` strings;
    ``inventory`` describes every limited handler found.
    """
    tree = ast.parse(source)
    aliases = _limiter_aliases(tree)
    offenders: list[str] = []
    inventory: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_limiter_decorator(d, aliases) for d in node.decorator_list):
            continue
        inventory.append(f"line {node.lineno}: {node.name}")
        names = _arg_names(node)
        if "request" not in names:
            offenders.append(f"line {node.lineno}: {node.name} (missing request: Request)")
            continue
        response = _response_param(node)
        if response is None:
            offenders.append(f"line {node.lineno}: {node.name} (missing response: Response)")
            continue
        if response.annotation is None or _annotation_name(response.annotation) != "Response":
            offenders.append(
                f"line {node.lineno}: {node.name} (response must be annotated Response)"
            )
    return offenders, inventory


def test_every_rate_limited_handler_declares_a_response_parameter() -> None:
    endpoint_files = sorted(ENDPOINTS_DIR.glob("*.py"))
    assert endpoint_files, f"no endpoint modules found under {ENDPOINTS_DIR}"

    offenders: list[str] = []
    inventory: list[str] = []
    for path in endpoint_files:
        file_offenders, file_inventory = scan_limited_handlers(path.read_text(encoding="utf-8"))
        offenders.extend(f"{path.name}: {msg}" for msg in file_offenders)
        inventory.extend(f"{path.name}: {msg}" for msg in file_inventory)

    assert offenders == [], (
        "Rate-limited handlers must declare `response: Response`; slowapi raises "
        "on the success path otherwise (HTTP 500):\n" + "\n".join(offenders)
    )
    assert len(inventory) >= MIN_LIMITED_HANDLERS, (
        "The rate-limit inventory unexpectedly shrank; the scanner may be "
        f"broken. Found {len(inventory)} limited handlers:\n" + "\n".join(inventory)
    )


def test_scanner_flags_a_handler_missing_the_response_parameter() -> None:
    """Self-test: the guard must fail on the exact R7 defect."""
    source = """
from fastapi import APIRouter, Request
from app.core.rate_limit import limiter

router = APIRouter()

@router.get("/things")
@limiter.limit("10/minute")
async def list_things(request: Request):
    return []
"""
    offenders, inventory = scan_limited_handlers(source)

    assert len(inventory) == 1
    assert len(offenders) == 1
    assert "list_things" in offenders[0]
    assert "response" in offenders[0]


def test_scanner_flags_a_handler_missing_the_request_parameter() -> None:
    source = """
from fastapi import APIRouter, Response
from app.core.rate_limit import limiter

router = APIRouter()

@router.get("/things")
@limiter.limit("10/minute")
async def list_things(response: Response):
    return []
"""
    offenders, _ = scan_limited_handlers(source)

    assert len(offenders) == 1
    assert "request" in offenders[0]


def test_scanner_accepts_a_correctly_declared_handler() -> None:
    source = """
from fastapi import APIRouter, Request, Response
from app.core.rate_limit import limiter

router = APIRouter()

@router.get("/things")
@limiter.limit("10/minute")
async def list_things(request: Request, response: Response):
    return []
"""
    offenders, inventory = scan_limited_handlers(source)
    assert offenders == []
    assert len(inventory) == 1
    assert "list_things" in inventory[0]


def test_scanner_flags_a_real_handler_when_the_parameter_is_removed() -> None:
    """Controlled mutation of the real source: the guard catches the R7 defect.

    ``ai.py`` previously omitted the parameter on all five handlers. Removing it
    from the current file (in memory only) must make the scanner report that
    handler, proving the guard is not vacuously green.
    """
    source = (ENDPOINTS_DIR / "ai.py").read_text(encoding="utf-8")
    assert "response: Response" in source
    mutated = source.replace("    response: Response,\n", "", 1)

    offenders, inventory = scan_limited_handlers(mutated)

    assert len(offenders) == 1
    assert "get_ai_settings" in offenders[0]
    assert "response" in offenders[0]
    assert len(inventory) == 5


def test_scanner_covers_aliased_limiter_decorators() -> None:
    """Aliased wrappers must not silently escape the guard."""
    source = """
from fastapi import APIRouter, Request, Response
from app.core.rate_limit import limiter as rl

router = APIRouter()
strict = rl.limit("5/minute")

@router.get("/aliased")
@strict
async def aliased(request: Request):
    return []
"""
    offenders, inventory = scan_limited_handlers(source)

    assert len(inventory) == 1
    assert len(offenders) == 1
    assert "aliased" in offenders[0]


@pytest.mark.parametrize(
    "decorator", ["limiter.limit('1/second')", "limiter.shared_limit('1/second', scope='x')"]
)
def test_scanner_covers_both_limiter_decorators(decorator: str) -> None:
    source = f"""
from fastapi import APIRouter, Request
from app.core.rate_limit import limiter

router = APIRouter()

@router.get("/limited")
@{decorator}
async def limited(request: Request):
    return []
"""
    offenders, inventory = scan_limited_handlers(source)

    assert len(inventory) == 1
    assert len(offenders) == 1
