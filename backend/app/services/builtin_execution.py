"""In-process workflow execution engine for the ``builtin`` adapter.

Runs a declarative, JSON-only step definition against the execution input.
It is deliberately stdlib-only (no eval/exec, no expression language): every
operation is a whitelisted, side-effect-free step so a misconfigured workflow
can never execute arbitrary code or mutate anything outside the result payload.

Definition format (stored in ``workflows.definition`` when
``execution_mode='builtin'``)::

    {
      "steps": [
        {"type": "copy", "id": "lead", "from": "input.lead", "to": "lead"},
        {"type": "set", "id": "greeting",
         "value": "Hello {{ lead.first_name }}"},
        {"type": "condition", "id": "segment",
         "if": {"path": "lead.score", "op": "gte", "value": 50},
         "then": [{"type": "set", "key": "segment", "value": "hot"}],
         "else": [{"type": "set", "key": "segment", "value": "cold"}]},
        {"type": "error_if", "id": "email",
         "message": "lead.email is required",
         "if": {"path": "lead.email", "op": "missing"}}
      ],
      "output_key": "lead"
    }

Steps share a ``context`` that starts as ``{"input": <execution input>}`` and
accumulate named results. ``output_key`` selects which context value becomes
the execution output; when omitted the whole context is returned.

Guards / templates read dotted paths (``a.b.c``) resolved against the context.
Templates use ``{{ path }}`` with an optional ``?? default`` fallback. No path
may contain characters outside ``[A-Za-z0-9_]``.
"""
from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from typing import Any

from app.core.config import settings

logger = logging.getLogger("agencyos.automation.builtin")

_KEY_RE = re.compile(r"[A-Za-z0-9_]+")
_TEMPLATE_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_STEP_TYPES = frozenset({"set", "copy", "condition", "error_if"})
_COMPARISON_OPS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte"})
_COLLECTION_OPS = frozenset({"in", "not_in", "contains"})
_PRESENCE_OPS = frozenset({"exists", "missing"})
_GUARD_OPS = _COMPARISON_OPS | _COLLECTION_OPS | _PRESENCE_OPS


class BuiltinExecutionError(Exception):
    """Raised for invalid definitions and runtime step failures."""


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "<missing>"


_MISSING = _Missing()


def _check_budget(budget: list[int], limit: int) -> None:
    budget[0] += 1
    if budget[0] > limit:
        raise BuiltinExecutionError(f"definition exceeds the {limit} step limit")


def _validate_path(path: Any, *, where: str) -> str:
    if not isinstance(path, str) or not path:
        raise BuiltinExecutionError(f"{where} must be a non-empty dotted path")
    for part in path.split("."):
        if not _KEY_RE.fullmatch(part):
            raise BuiltinExecutionError(
                f"{where} segment {part!r} is invalid (use [A-Za-z0-9_])"
            )
    return path


def _validate_key(key: Any, *, where: str) -> str:
    if not isinstance(key, str) or not key:
        raise BuiltinExecutionError(f"{where} must be a non-empty string key")
    return key


def _validate_guard(guard: Any) -> dict[str, Any]:
    if not isinstance(guard, dict):
        raise BuiltinExecutionError("guard 'if' must be an object")
    path = _validate_path(guard.get("path"), where="guard.path")
    op = guard.get("op")
    if not isinstance(op, str) or op not in _GUARD_OPS:
        raise BuiltinExecutionError(
            f"guard.op must be one of {sorted(_GUARD_OPS)}"
        )
    result = {"path": path, "op": op, "value": guard.get("value")}
    if op in _COLLECTION_OPS and not isinstance(result["value"], list):
        raise BuiltinExecutionError(f"guard.op {op!r} requires a list value")
    return result


def _validate_step(
    step: Any, *, depth: int, budget: list[int], max_steps: int, max_depth: int
) -> None:
    if not isinstance(step, dict):
        raise BuiltinExecutionError("each step must be an object")
    _check_budget(budget, max_steps)
    step_type = step.get("type")
    if step_type not in _STEP_TYPES:
        raise BuiltinExecutionError(
            f"unknown step type {step_type!r} (use {sorted(_STEP_TYPES)})"
        )
    if step_type in ("set", "copy", "condition", "error_if") and "key" in step:
        if not isinstance(step["key"], str):
            raise BuiltinExecutionError("step.key must be a string")
    if step_type == "set":
        if "key" not in step or "value" not in step:
            raise BuiltinExecutionError("set steps require 'key' and 'value'")
        _validate_key(step["key"], where="step.key")
    elif step_type == "copy":
        if "from" not in step or "to" not in step:
            raise BuiltinExecutionError("copy steps require 'from' and 'to'")
        _validate_path(step["from"], where="step.from")
        _validate_key(step["to"], where="step.to")
    elif step_type == "condition":
        if "if" not in step:
            raise BuiltinExecutionError("condition steps require an 'if' guard")
        _validate_guard(step["if"])
        then = step.get("then", [])
        if not isinstance(then, list):
            raise BuiltinExecutionError("condition.then must be a list of steps")
        if depth + 1 > max_depth:
            raise BuiltinExecutionError(
                f"condition nesting exceeds the {max_depth} depth limit"
            )
        for sub in then:
            _validate_step(
                sub,
                depth=depth + 1,
                budget=budget,
                max_steps=max_steps,
                max_depth=max_depth,
            )
        else_branch = step.get("else", [])
        if not isinstance(else_branch, list):
            raise BuiltinExecutionError("condition.else must be a list of steps")
        for sub in else_branch:
            _validate_step(
                sub,
                depth=depth + 1,
                budget=budget,
                max_steps=max_steps,
                max_depth=max_depth,
            )
    elif step_type == "error_if":
        if "message" not in step or not isinstance(step["message"], str) or not step["message"]:
            raise BuiltinExecutionError("error_if steps require a non-empty 'message'")
        if "if" not in step:
            raise BuiltinExecutionError("error_if steps require an 'if' guard")
        _validate_guard(step["if"])


def validate_builtin_definition(
    definition: Any,
    *,
    max_steps: int | None = None,
    max_depth: int | None = None,
) -> None:
    """Structurally validate a builtin definition (fail-fast at write time).

    Raises :class:`BuiltinExecutionError` when the definition cannot run.
    """
    if not isinstance(definition, dict):
        raise BuiltinExecutionError("workflow definition must be an object")
    steps = definition.get("steps", [])
    if not isinstance(steps, list):
        raise BuiltinExecutionError("definition.steps must be a list")
    budget = [0]
    for step in steps:
        _validate_step(
            step,
            depth=1,
            budget=budget,
            max_steps=max_steps if max_steps is not None else settings.BUILTIN_MAX_STEPS,
            max_depth=max_depth if max_depth is not None else settings.BUILTIN_MAX_CONDITION_DEPTH,
        )


def _resolve(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if not _KEY_RE.fullmatch(part):
            raise BuiltinExecutionError(
                f"path segment {part!r} is invalid (use [A-Za-z0-9_])"
            )
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def _render_template(
    context: dict[str, Any],
    text: str,
    *,
    max_length: int,
) -> str:
    if "{{" not in text:
        return text
    if len(text) > max_length:
        raise BuiltinExecutionError(
            f"template exceeds the {max_length} character limit"
        )

    def _sub(match: re.Match[str]) -> str:
        expression = match.group(1).strip()
        default: str | None = None
        if "??" in expression:
            path, _, raw_default = expression.partition("??")
            path = path.strip()
            default = raw_default.strip() or None
        else:
            path = expression
        value = _resolve(context, path)
        if value is _MISSING:
            if default is not None:
                return default
            raise BuiltinExecutionError(f"template path not found: {path}")
        return _stringify(value)

    return _TEMPLATE_RE.sub(_sub, text)


def _evaluate_guard(context: dict[str, Any], guard: dict[str, Any]) -> bool:
    path = guard["path"]
    op = guard["op"]
    expected: Any = guard.get("value")
    actual = _resolve(context, path)

    if op in _PRESENCE_OPS:
        present = actual is not _MISSING
        return present if op == "exists" else not present

    if actual is _MISSING:
        return False

    if op in _COMPARISON_OPS:
        if op == "eq":
            return actual == expected
        if op == "ne":
            return actual != expected
        try:
            if op == "gt":
                return actual > expected
            if op == "gte":
                return actual >= expected
            if op == "lt":
                return actual < expected
            return actual <= expected
        except TypeError as exc:
            raise BuiltinExecutionError(
                f"guard values at {path!r} are not comparable"
            ) from exc

    if op in ("in", "not_in"):
        if isinstance(actual, list):
            found = any(item in expected for item in actual)
        else:
            found = actual in expected
        return found if op == "in" else not found

    if op == "contains":
        if isinstance(actual, (str, list)) and isinstance(expected, str):
            return expected in actual
        raise BuiltinExecutionError(
            f"guard {path!r} cannot be checked with 'contains'"
        )
    raise BuiltinExecutionError(f"unsupported guard operator {op!r}")  # pragma: no cover


def _check_result_size(context: dict[str, Any], *, limit: int) -> None:
    size = len(json.dumps(context, separators=(",", ":"), ensure_ascii=False))
    if size > limit:
        raise BuiltinExecutionError(
            f"result exceeds the {limit} byte size limit"
        )


def _run_steps(
    steps: list[Any],
    context: dict[str, Any],
    *,
    budget: list[int],
    max_steps: int,
    max_depth: int,
    max_template_length: int,
    depth: int,
) -> None:
    for step in steps:
        _check_budget(budget, max_steps)
        step_type = step["type"]
        if step_type == "set":
            value = step["value"]
            if isinstance(value, str) and "{{" in value:
                context[step["key"]] = _render_template(
                    context,
                    value,
                    max_length=max_template_length,
                )
            else:
                context[step["key"]] = deepcopy(value)
        elif step_type == "copy":
            resolved = _resolve(context, step["from"])
            if resolved is _MISSING:
                raise BuiltinExecutionError(
                    f"copy source path not found: {step['from']}"
                )
            context[step["to"]] = deepcopy(resolved)
        elif step_type == "condition":
            if depth + 1 > max_depth:
                raise BuiltinExecutionError(
                    f"condition nesting exceeds the {max_depth} depth limit"
                )
            branch = step["then"] if _evaluate_guard(context, step["if"]) else step.get("else", [])
            _run_steps(
                branch,
                context,
                budget=budget,
                max_steps=max_steps,
                max_depth=max_depth,
                max_template_length=max_template_length,
                depth=depth + 1,
            )
        elif step_type == "error_if":
            if _evaluate_guard(context, step["if"]):
                raise BuiltinExecutionError(step["message"])


def run_builtin_definition(
    definition: dict[str, Any],
    input_data: dict[str, Any],
    *,
    max_steps: int | None = None,
    max_depth: int | None = None,
    max_template_length: int | None = None,
    max_result_size: int | None = None,
) -> dict[str, Any]:
    """Execute a builtin definition and return the result payload.

    The engine is deterministic and side-effect free; a crash mid-execution
    leaves nothing behind, so retries (driven by the execution worker's
    existing state machine) always re-run from the same input.
    """
    if max_steps is None:
        max_steps = settings.BUILTIN_MAX_STEPS
    if max_depth is None:
        max_depth = settings.BUILTIN_MAX_CONDITION_DEPTH
    if max_template_length is None:
        max_template_length = settings.BUILTIN_MAX_TEMPLATE_LENGTH
    if max_result_size is None:
        max_result_size = settings.BUILTIN_MAX_RESULT_SIZE_BYTES

    steps = definition.get("steps", [])
    if not isinstance(steps, list):
        raise BuiltinExecutionError("definition.steps must be a list")

    context: dict[str, Any] = {"input": deepcopy(input_data)}
    budget = [0]
    _run_steps(
        steps,
        context,
        budget=budget,
        max_steps=max_steps,
        max_depth=max_depth,
        max_template_length=max_template_length,
        depth=1,
    )
    _check_result_size(context, limit=max_result_size)

    output_key = definition.get("output_key")
    if output_key is not None:
        _validate_key(output_key, where="definition.output_key")
        if output_key not in context:
            raise BuiltinExecutionError(f"output_key {output_key!r} was not produced")
        return {output_key: context[output_key]}
    return context
