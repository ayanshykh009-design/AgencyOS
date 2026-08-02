"""Validate n8n workflow exports are structurally sound.

n8n has no public JSON schema, so full validation requires importing into an
instance (see workflows/n8n/README.md). These checks enforce the invariants we
control in version control: valid JSON, required fields, unique node ids, and
connections that reference real nodes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_N8N_DIR = _REPO_ROOT / "workflows" / "n8n"

_WORKFLOW_DIRS = ("workflows", "templates")


def _all_workflow_files() -> list[Path]:
    files: list[Path] = []
    for subdir in _WORKFLOW_DIRS:
        target = _N8N_DIR / subdir
        if target.is_dir():
            files.extend(target.glob("*.json"))
    return sorted(files)


@pytest.fixture(scope="module")
def workflows() -> list[tuple[str, dict]]:
    return [
        (str(path.relative_to(_REPO_ROOT)), json.loads(path.read_text()))
        for path in _all_workflow_files()
    ]


def test_workflow_files_exist() -> None:
    assert _all_workflow_files(), f"expected workflow JSONs under {_N8N_DIR}"


def test_workflow_top_level_shape(workflows: list[tuple[str, dict]]) -> None:
    for name, data in workflows:
        assert isinstance(data, dict), f"{name} must be a JSON object"
        assert isinstance(data.get("name"), str) and data["name"].strip(), f"{name}: name required"
        assert isinstance(data.get("nodes"), list) and data["nodes"], f"{name}: nodes required"
        assert isinstance(data.get("connections"), dict), f"{name}: connections required"
        assert data.get("active") is False, f"{name}: workflows must import inactive"


def test_node_fields_and_unique_ids(workflows: list[tuple[str, dict]]) -> None:
    for name, data in workflows:
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        for node in data["nodes"]:
            assert isinstance(node, dict), f"{name}: node must be an object"
            for field in ("name", "type", "typeVersion", "position"):
                assert field in node, f"{name}: node {node.get('name')} missing {field}"
            assert isinstance(node["name"], str) and node["name"].strip()
            assert node["name"] not in seen_names, f"{name}: duplicate node name {node['name']}"
            seen_names.add(node["name"])
            assert node["id"] not in seen_ids, f"{name}: duplicate node id {node['id']}"
            seen_ids.add(node["id"])
            assert isinstance(node["typeVersion"], (int, float)), (
                f"{name}: {node['name']} typeVersion"
            )
            assert len(node["position"]) == 2, f"{name}: {node['name']} position"


def test_connections_reference_real_nodes(workflows: list[tuple[str, dict]]) -> None:
    for name, data in workflows:
        node_names = {node["name"] for node in data["nodes"]}
        for source, outputs in data["connections"].items():
            assert source in node_names, f"{name}: connection from unknown node {source}"
            for main_outputs in outputs.get("main", []):
                for link in main_outputs:
                    target = link.get("node")
                    assert target in node_names, f"{name}: connection to unknown node {target}"
                    assert link.get("type") == "main", (
                        f"{name}: unexpected connection type {link.get('type')}"
                    )


def test_no_secrets_in_workflows(workflows: list[tuple[str, dict]]) -> None:
    raw_blob = "\n".join(json.dumps(data) for _, data in workflows)
    for secret in ("-----BEGIN", "api_key:", "Authorization: Bearer ", "password:"):
        assert secret not in raw_blob, f"found hardcoded secret pattern {secret!r} in a workflow"
