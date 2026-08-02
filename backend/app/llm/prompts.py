"""Versioned prompt rendering from the ``prompts/`` library.

Prompts are versioned Markdown files with a small front-matter header
(``name``, ``version``, ``status``, ``model``, ...). :class:`PromptManager`
loads them by ``name@version`` and renders ``{{ variable }}`` placeholders
with caller-supplied values, so business logic never embeds prompt text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR

# Repository root is two levels up from app/llm (backend/app -> backend -> root).
_PROMPTS_DIR = BACKEND_DIR.parent.parent / "prompts"

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
# Dot-paths like {{ prospect.firstName }} or {{ prospect.address.city }}.
_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def _resolve(path: str, variables: dict) -> Any:
    """Resolve a dotted variable path against the variables mapping."""
    current: Any = variables
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.lstrip("0123456789"):
            continue
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                raise KeyError(f"prompt index out of range: {part}")
        else:
            raise KeyError(f"prompt missing variable: {path}")
    return current


def _substitute(body: str, variables: dict) -> str:
    def _replace(match: re.Match[str]) -> str:
        value = _resolve(match.group(1), variables)
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    return _VAR.sub(_replace, body)


@dataclass(frozen=True)
class PromptMeta:
    name: str
    version: str
    status: str
    model: str
    tags: list[str] = field(default_factory=list)
    purpose: str | None = None
    source: str = ""


@dataclass(frozen=True)
class Prompt:
    meta: PromptMeta
    body: str


def _parse_front_matter(text: str, source: str = "") -> tuple[PromptMeta, str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        raise ValueError(f"prompt file has no YAML front-matter: {source}")
    header, body = match.groups()
    fields: dict[str, str] = {}
    for line in header.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    tags = [t.strip() for t in fields.get("tags", "").strip("[]").split(",") if t.strip()]
    meta = PromptMeta(
        name=fields.get("name", ""),
        version=fields.get("version", ""),
        status=fields.get("status", ""),
        model=fields.get("model", ""),
        tags=tags,
        purpose=fields.get("purpose"),
        source=source,
    )
    return meta, body


def _find_prompt(root: Path, name: str, version: str) -> Path:
    """Locate the Markdown file whose front-matter name/version match."""
    if not root.is_dir():
        raise FileNotFoundError(f"prompts directory not found: {root}")
    for path in root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            meta, _ = _parse_front_matter(text, source=str(path))
        except ValueError:
            continue
        if meta.name == name and meta.version == version:
            return path
    raise FileNotFoundError(f"prompt not found: {name}@{version}")


class PromptManager:
    """Load and render versioned prompts from disk.

    Each instance is bound to a prompts root (defaults to the repo ``prompts/``
    dir). Results are cached per ``(name, version)`` for the process lifetime.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else _PROMPTS_DIR

    def load(self, name: str, version: str) -> Prompt:
        path = _find_prompt(self._root, name, version)
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(text, source=str(path))
        return Prompt(meta=meta, body=body)

    def render(self, name: str, version: str, variables: dict | None = None) -> str:
        prompt = self.load(name, version)
        return _substitute(prompt.body, variables or {})

    def render_message(
        self, name: str, version: str, variables: dict | None = None
    ) -> tuple[PromptMeta, str]:
        """Return ``(meta, rendered_body)`` — useful for auditing the prompt."""
        prompt = self.load(name, version)
        return prompt.meta, _substitute(prompt.body, variables or {})
