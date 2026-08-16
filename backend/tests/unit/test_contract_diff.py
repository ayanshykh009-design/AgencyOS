"""Regression tests for the M10 contract-diff script.

These verify the script's static parsing of the frontend service layer:
  * literal backend routes are matched,
  * ``API_BASE`` (and other file-local string constants) are resolved,
  * nested / multiple template constants resolve correctly,
  * backend path parameters (``{id}``) compare equal to frontend ``${id}``,
  * genuine missing/wrong routes are still flagged as drift,
  * query-string-in-template (e.g. ``/pipeline/close-reasons${qs}``) is NOT
    falsely reported as drift.
"""

import sys
from pathlib import Path

# Make the CI script importable without importing the application package.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "ci"))
import contract_diff as cd  # noqa: E402


def test_normalize_path_params():
    assert cd.normalize("/leads/{lead_id}") == "/api/v1/leads/*"
    assert cd.normalize("/leads/:id") == "/api/v1/leads/*"


def test_normalize_query_string_template_is_not_a_segment():
    # `/pipeline/close-reasons${qs}` where `qs` is a "?query" string must keep
    # the static segment and drop the template variable.
    assert cd.normalize("/pipeline/close-reasons${qs}") == "/api/v1/pipeline/close-reasons"


def test_normalize_standalone_template_var_is_wildcard():
    assert cd.normalize("${API_BASE}/operational/summary") == "/api/v1/*/operational/summary"


def test_collect_and_expand_constants():
    text = 'const API_BASE = "/monitoring";\nconst OTHER = "/intelligence";'
    consts = cd.collect_constants(text)
    assert consts["API_BASE"] == "/monitoring"
    assert cd.expand_constants("${API_BASE}/x", consts) == "/monitoring/x"


def test_api_base_constant_resolution():
    text = (
        'const API_BASE = "/monitoring";\n'
        "export const f = () => apiFetch<Summary>(`${API_BASE}/operational/summary`);\n"
    )
    calls = cd.extract_calls_from_text(text)
    assert "/api/v1/monitoring/operational/summary" in calls
    routes = {"/api/v1/monitoring/operational/summary": {"GET"}}
    drift, _, _ = cd.analyze(calls, routes)
    assert drift == []


def test_nested_template_constant():
    text = (
        'const API_BASE = "/monitoring";\n'
        "export const f = () => apiFetch<X>(`${API_BASE}/${id}/x`);\n"
    )
    calls = cd.extract_calls_from_text(text)
    assert "/api/v1/monitoring/*/x" in calls


def test_multiple_constants():
    text = (
        'const A = "/x";\nconst B = "/y";\n'
        "export const f = () => apiFetch<X>(`${A}/${B}/z`);\n"
    )
    calls = cd.extract_calls_from_text(text)
    assert "/api/v1/x/y/z" in calls


def test_backend_path_param_matches_frontend():
    routes = {"/api/v1/leads/*": {"GET", "PATCH", "DELETE"}}
    calls = {"/api/v1/leads/*": {"GET"}}
    drift, _, _ = cd.analyze(calls, routes)
    assert drift == []


def test_genuine_wrong_route_is_flagged():
    routes = {"/api/v1/leads": {"GET"}}
    calls = {"/api/v1/bogus": {"GET"}}
    drift, _, _ = cd.analyze(calls, routes)
    assert drift == ["FE calls unknown route: GET /api/v1/bogus"]


def test_missing_path_param_route_is_flagged():
    routes = {"/api/v1/leads": {"GET"}}
    calls = {"/api/v1/leads/*": {"GET"}}
    drift, _, _ = cd.analyze(calls, routes)
    assert drift == ["FE calls unknown route: GET /api/v1/leads/*"]


def test_query_string_template_false_positive_prevention():
    text = (
        "export const f = () => apiFetch<CloseReason[]>(`/pipeline/close-reasons${qs}`);\n"
    )
    calls = cd.extract_calls_from_text(text)
    assert "/api/v1/pipeline/close-reasons" in calls
    assert "/api/v1/pipeline/*" not in calls
    routes = {"/api/v1/pipeline/close-reasons": {"GET"}}
    drift, _, _ = cd.analyze(calls, routes)
    assert drift == []
