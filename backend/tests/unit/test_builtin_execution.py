"""Unit tests: builtin (in-process) execution engine."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.builtin_execution import (
    BuiltinExecutionError,
    run_builtin_definition,
    validate_builtin_definition,
)


def _input() -> dict:
    return {
        "lead": {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "score": 70,
            "tags": ["engineering", "founder"],
        },
        "source": "webform",
    }


def test_empty_definition_returns_input_context() -> None:
    result = run_builtin_definition({}, _input())
    assert result == {"input": _input()}


def test_steps_run_in_order_and_accumulate() -> None:
    definition = {
        "steps": [
            {"type": "copy", "from": "input.lead", "to": "lead"},
            {"type": "set", "key": "greeting", "value": "Hi {{ lead.first_name }}"},
        ]
    }
    result = run_builtin_definition(definition, _input())
    assert result["lead"]["email"] == "ada@example.com"
    assert result["greeting"] == "Hi Ada"


def test_input_is_not_mutated() -> None:
    definition = {
        "steps": [
            {"type": "copy", "from": "input.lead", "to": "lead"},
            {"type": "set", "key": "lead.first_name", "value": "x"},
        ]
    }
    run_builtin_definition(definition, _input())
    assert _input()["lead"]["first_name"] == "Ada"


def test_set_writes_literal_value_not_template() -> None:
    definition = {
        "steps": [
            {"type": "set", "key": "kind", "value": "{{ input.source }}"},
            {"type": "set", "key": "literal", "value": "no braces here"},
        ]
    }
    result = run_builtin_definition(definition, _input())
    assert result["kind"] == "webform"
    assert result["literal"] == "no braces here"


def test_template_default_used_for_missing_path() -> None:
    definition = {
        "steps": [
            {
                "type": "set",
                "key": "phone",
                "value": "{{ input.lead.phone ?? unknown }}",
            }
        ]
    }
    result = run_builtin_definition(definition, _input())
    assert result["phone"] == "unknown"


def test_template_missing_path_without_default_raises() -> None:
    definition = {
        "steps": [
            {"type": "set", "key": "phone", "value": "{{ input.lead.phone }}"}
        ]
    }
    with pytest.raises(BuiltinExecutionError, match="phone"):
        run_builtin_definition(definition, _input())


def test_template_rejects_invalid_path_segment() -> None:
    definition = {
        "steps": [
            {"type": "set", "key": "x", "value": "{{ input.lead[0] }}"}
        ]
    }
    with pytest.raises(BuiltinExecutionError, match="segment"):
        run_builtin_definition(definition, _input())


def test_template_renders_json_like_values() -> None:
    definition = {
        "steps": [
            {"type": "copy", "from": "input.lead.tags", "to": "tags"},
            {"type": "set", "key": "tags_txt", "value": "{{ tags }}"},
        ]
    }
    result = run_builtin_definition(definition, _input())
    assert result["tags_txt"] == '["engineering","founder"]'


def test_copy_missing_source_raises() -> None:
    definition = {
        "steps": [
            {"type": "copy", "from": "input.nope", "to": "x"}
        ]
    }
    with pytest.raises(BuiltinExecutionError, match="not found"):
        run_builtin_definition(definition, _input())


def test_copy_deep_copies_not_shares_references() -> None:
    definition = {
        "steps": [
            {"type": "copy", "from": "input.lead", "to": "lead"},
            {"type": "set", "key": "lead", "value": {"name": "replaced"}},
        ]
    }
    result = run_builtin_definition(definition, _input())
    assert result["lead"] == {"name": "replaced"}
    assert _input()["lead"]["first_name"] == "Ada"


@pytest.mark.parametrize(
    ("path", "op", "value", "expected"),
    [
        ("input.lead.score", "eq", 70, True),
        ("input.lead.score", "eq", 71, False),
        ("input.lead.score", "ne", 71, True),
        ("input.lead.score", "gt", 50, True),
        ("input.lead.score", "gte", 70, True),
        ("input.lead.score", "lt", 70, False),
        ("input.lead.score", "lte", 70, True),
        ("input.lead.tags", "in", ["engineering", "founder"], True),
        ("input.lead.tags", "not_in", ["banker"], True),
        ("input.lead.tags", "contains", "founder", True),
        ("input.lead.tags", "contains", "banker", False),
        ("input.lead.score", "exists", None, True),
    ],
)
def test_condition_ops_select_branch(
    path: str, op: str, value: object, expected: bool
) -> None:
    definition = {
        "steps": [
            {
                "type": "condition",
                "if": {"path": path, "op": op, "value": value},
                "then": [{"type": "set", "key": "outcome", "value": "hit"}],
                "else": [{"type": "set", "key": "outcome", "value": "miss"}],
            }
        ]
    }
    result = run_builtin_definition(definition, _input())
    assert result["outcome"] == ("hit" if expected else "miss")


def test_condition_missing_guard_falls_through_to_else() -> None:
    definition = {
        "steps": [
            {
                "type": "condition",
                "if": {"path": "input.lead.phone", "op": "eq", "value": "123"},
                "then": [{"type": "set", "key": "outcome", "value": "hit"}],
                "else": [{"type": "set", "key": "outcome", "value": "miss"}],
            }
        ]
    }
    result = run_builtin_definition(definition, _input())
    assert result["outcome"] == "miss"


def test_condition_missing_presence_ops() -> None:
    definition = {
        "steps": [
            {
                "type": "condition",
                "if": {"path": "input.lead.phone", "op": "missing"},
                "then": [{"type": "set", "key": "has_phone", "value": "no"}],
            }
        ]
    }
    result = run_builtin_definition(definition, _input())
    assert result["has_phone"] == "no"


def test_condition_nesting_is_bounded() -> None:
    nested = {"type": "set", "key": "leaf", "value": "ok"}
    for _ in range(settings.BUILTIN_MAX_CONDITION_DEPTH + 2):
        nested = {
            "type": "condition",
            "if": {"path": "input.source", "op": "eq", "value": "webform"},
            "then": [nested],
        }
    definition = {"steps": [nested]}
    with pytest.raises(BuiltinExecutionError, match="depth"):
        run_builtin_definition(definition, _input())


def test_error_if_fails_execution_with_message() -> None:
    definition = {
        "steps": [
            {
                "type": "error_if",
                "message": "score too low",
                "if": {"path": "input.lead.score", "op": "lt", "value": 100},
            }
        ]
    }
    with pytest.raises(BuiltinExecutionError, match="score too low"):
        run_builtin_definition(definition, _input())


def test_error_if_does_not_raise_when_guard_false() -> None:
    definition = {
        "steps": [
            {
                "type": "error_if",
                "message": "score too low",
                "if": {"path": "input.lead.score", "op": "gt", "value": 100},
            }
        ]
    }
    assert run_builtin_definition(definition, _input())["input"]


def test_output_key_returns_only_that_value() -> None:
    definition = {
        "steps": [
            {"type": "copy", "from": "input.lead", "to": "lead"},
            {"type": "set", "key": "greeting", "value": "Hi {{ lead.first_name }}"},
        ],
        "output_key": "greeting",
    }
    result = run_builtin_definition(definition, _input())
    assert result == {"greeting": "Hi Ada"}


def test_output_key_missing_raises() -> None:
    definition = {"steps": [], "output_key": "nope"}
    with pytest.raises(BuiltinExecutionError, match="output_key"):
        run_builtin_definition(definition, _input())


def test_step_budget_limit_enforced() -> None:
    steps = [{"type": "set", "key": f"k{i}", "value": str(i)} for i in range(60)]
    definition = {"steps": steps}
    with pytest.raises(BuiltinExecutionError, match="step limit"):
        run_builtin_definition(definition, _input(), max_steps=50)


def test_result_size_limit_enforced() -> None:
    definition = {
        "steps": [
            {"type": "set", "key": "blob", "value": "x" * 1000}
        ]
    }
    with pytest.raises(BuiltinExecutionError, match="size limit"):
        run_builtin_definition(definition, _input(), max_result_size=100)


def test_template_length_limit_enforced() -> None:
    definition = {
        "steps": [
            {"type": "set", "key": "big", "value": "{{ input.source }}" + "x" * 100}
        ]
    }
    with pytest.raises(BuiltinExecutionError, match="character limit"):
        run_builtin_definition(definition, _input(), max_template_length=50)


# --- Structural validation (fail-fast at write time) -------------------------


def test_validate_rejects_non_object_definition() -> None:
    with pytest.raises(BuiltinExecutionError):
        validate_builtin_definition([])


def test_validate_rejects_unknown_step_type() -> None:
    with pytest.raises(BuiltinExecutionError, match="unknown step type"):
        validate_builtin_definition({"steps": [{"type": "exec"}]})


def test_validate_set_requires_key_and_value() -> None:
    with pytest.raises(BuiltinExecutionError, match="'key' and 'value'"):
        validate_builtin_definition({"steps": [{"type": "set"}]})


def test_validate_copy_requires_from_and_to() -> None:
    with pytest.raises(BuiltinExecutionError, match="'from' and 'to'"):
        validate_builtin_definition({"steps": [{"type": "copy", "from": "a"}]})


def test_validate_condition_requires_if_and_lists() -> None:
    with pytest.raises(BuiltinExecutionError, match="'if' guard"):
        validate_builtin_definition({"steps": [{"type": "condition"}]})
    with pytest.raises(BuiltinExecutionError, match="then"):
        validate_builtin_definition(
            {
                "steps": [
                    {
                        "type": "condition",
                        "if": {"path": "a", "op": "eq", "value": 1},
                        "then": "not-a-list",
                    }
                ]
            }
        )


def test_validate_error_if_requires_message() -> None:
    with pytest.raises(BuiltinExecutionError, match="'message'"):
        validate_builtin_definition(
            {"steps": [{"type": "error_if", "if": {"path": "a", "op": "exists"}}]}
        )


def test_validate_guard_op_whitelist() -> None:
    with pytest.raises(BuiltinExecutionError, match="guard.op"):
        validate_builtin_definition(
            {"steps": [{"type": "condition", "if": {"path": "a", "op": "sudo"}}]}
        )


def test_validate_collection_op_requires_list_value() -> None:
    with pytest.raises(BuiltinExecutionError, match="list value"):
        validate_builtin_definition(
            {"steps": [{"type": "condition", "if": {"path": "a", "op": "in", "value": "x"}}]}
        )


def test_validate_path_segments() -> None:
    with pytest.raises(BuiltinExecutionError, match="segment"):
        validate_builtin_definition(
            {"steps": [{"type": "copy", "from": "input.lead[0]", "to": "x"}]}
        )


def test_validate_nesting_depth() -> None:
    nested = {"type": "set", "key": "leaf", "value": "ok"}
    for _ in range(settings.BUILTIN_MAX_CONDITION_DEPTH + 1):
        nested = {
            "type": "condition",
            "if": {"path": "a", "op": "eq", "value": 1},
            "then": [nested],
        }
    with pytest.raises(BuiltinExecutionError, match="depth"):
        validate_builtin_definition({"steps": [nested]})


def test_validate_accepts_valid_definition() -> None:
    definition = {
        "steps": [
            {"type": "copy", "from": "input.lead", "to": "lead"},
            {"type": "set", "key": "greeting", "value": "Hi {{ lead.first_name }}"},
            {
                "type": "condition",
                "if": {"path": "lead.score", "op": "gte", "value": 50},
                "then": [{"type": "set", "key": "segment", "value": "hot"}],
            },
            {
                "type": "error_if",
                "message": "email required",
                "if": {"path": "lead.email", "op": "missing"},
            },
        ],
        "output_key": "lead",
    }
    validate_builtin_definition(definition)


def test_on_step_reports_started_and_completed() -> None:
    definition = {
        "steps": [
            {"type": "set", "key": "a", "value": "1", "id": "s1"},
            {"type": "copy", "from": "input.lead", "to": "lead", "id": "s2"},
        ]
    }
    calls: list[tuple[str, int, str | None]] = []

    run_builtin_definition(definition, _input(), on_step=lambda *c: calls.append(c))

    assert calls == [
        ("started", 1, "s1"),
        ("completed", 1, "s1"),
        ("started", 2, "s2"),
        ("completed", 2, "s2"),
    ]


def test_on_step_reports_failed_and_stops() -> None:
    definition = {
        "steps": [
            {"type": "set", "key": "a", "value": "1", "id": "s1"},
            {
                "type": "error_if",
                "message": "boom",
                "if": {"path": "input.source", "op": "eq", "value": "webform"},
                "id": "s2",
            },
        ]
    }
    calls: list[tuple[str, int, str | None]] = []

    with pytest.raises(BuiltinExecutionError, match="boom"):
        run_builtin_definition(definition, _input(), on_step=lambda *c: calls.append(c))

    assert calls[-1] == ("failed", 2, "s2")
    assert ("completed", 2, "s2") not in calls
