"""Unit tests for M4 memory classification (canonical 8 types + normalization)."""
from __future__ import annotations

import pytest

from app.memory.classification import (
    KNOWLEDGE_CATEGORIES,
    CanonicalMemoryType,
    classify_canonical_type,
    infer_scope,
    normalize_content,
)
from app.models.enums import MemoryScope, MemoryType


def test_knowledge_categories_are_the_four_long_term_buckets() -> None:
    assert KNOWLEDGE_CATEGORIES == {"founder", "business", "crm", "knowledge"}


def test_all_eight_canonical_types_reachable() -> None:
    got = {
        classify_canonical_type(MemoryType.LONG_TERM, MemoryScope.MANUAL, cat)
        for cat in KNOWLEDGE_CATEGORIES
    } | {
        classify_canonical_type(MemoryType.WORKING, scope)
        for scope in (
            MemoryScope.CONVERSATION,
            MemoryScope.RESEARCH,
            MemoryScope.WORKFLOW,
            MemoryScope.SHARED_CONTEXT,
        )
    }
    assert got == set(CanonicalMemoryType)


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("founder", CanonicalMemoryType.FOUNDER),
        ("business", CanonicalMemoryType.BUSINESS),
        ("crm", CanonicalMemoryType.CRM),
        ("knowledge", CanonicalMemoryType.KNOWLEDGE),
    ],
)
def test_long_term_maps_by_category(category: str, expected: CanonicalMemoryType) -> None:
    assert (
        classify_canonical_type(MemoryType.LONG_TERM, MemoryScope.MANUAL, category)
        is expected
    )


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (MemoryScope.CONVERSATION, CanonicalMemoryType.CONVERSATION),
        (MemoryScope.RESEARCH, CanonicalMemoryType.RESEARCH),
        (MemoryScope.WORKFLOW, CanonicalMemoryType.WORKFLOW),
        (MemoryScope.SHARED_CONTEXT, CanonicalMemoryType.SHARED_CONTEXT),
    ],
)
def test_working_maps_by_scope(scope: MemoryScope, expected: CanonicalMemoryType) -> None:
    assert classify_canonical_type(MemoryType.WORKING, scope) is expected


def test_long_term_with_unknown_category_falls_back_to_business() -> None:
    assert (
        classify_canonical_type(MemoryType.LONG_TERM, MemoryScope.MANUAL, "shopping")
        is CanonicalMemoryType.BUSINESS
    )


def test_working_with_unknown_scope_falls_back_to_research() -> None:
    assert classify_canonical_type(MemoryType.WORKING) is CanonicalMemoryType.RESEARCH


def test_infer_scope_recognizes_known_sources_case_insensitive() -> None:
    assert infer_scope("Workflow") is MemoryScope.WORKFLOW
    assert infer_scope("  conversation ") is MemoryScope.CONVERSATION


def test_infer_scope_defaults_to_research_for_unknown() -> None:
    assert infer_scope("web-scraper") is MemoryScope.RESEARCH
    assert infer_scope(None) is MemoryScope.RESEARCH
    assert infer_scope("") is MemoryScope.RESEARCH


def test_normalize_content_collapses_and_lowercases() -> None:
    assert normalize_content("  Hello   World\n  again  ") == "hello world again"


def test_normalize_content_truncates_to_max_len() -> None:
    collapsed = normalize_content("a b " * 100)
    truncated = normalize_content("a b " * 100, max_len=16)
    assert truncated == collapsed[:16]
    assert len(truncated) <= 16
