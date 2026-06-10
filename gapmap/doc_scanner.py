"""Phase 5 - Documentation scanner.

Checks whether each entity is documented by scanning:

1. All Markdown files in the repo (``docs/``, ``adr/``, ``*.md``)
2. Docstrings anywhere in the entity's own source file

An entity is **documented** when its exact ``entity_name`` appears in
either source, matched with **case-sensitive word boundaries** (so
``route`` does not match ``router`` and ``Auth`` does not match
``AuthError``).

A **highly complex** entity (LOC >= ``COMPLEX_ENTITY_MIN_LOC``) that
is not documented is flagged as **undocumented**.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from gapmap.parser import SKIP_DIRS, EntityInfo, _safe_read

# Entities with at least this many non-blank lines are "highly complex"
# and must be documented to avoid being flagged.
COMPLEX_ENTITY_MIN_LOC = 5


@dataclass
class DocScan:
    doc_files: List[str] = field(default_factory=list)
    mentions: Dict[str, List[str]] = field(default_factory=dict)
    # mentions: entity key -> sources that reference the entity by name
    # (markdown paths or "docstring:<file>")

    def is_documented(self, key: str) -> bool:
        """True when the entity name appears in markdown or file docstrings."""
        return bool(self.mentions.get(key))

    def is_complex(self, entity: EntityInfo) -> bool:
        """True when the entity exceeds the complexity LOC threshold."""
        return entity.loc >= COMPLEX_ENTITY_MIN_LOC

    def is_undocumented(self, entity: EntityInfo) -> bool:
        """Highly complex entity with no markdown or docstring mention."""
        return self.is_complex(entity) and not self.is_documented(entity.key)


def scan_entity_docs(root: str | Path, entities: Iterable[EntityInfo]) -> DocScan:
    """Scan markdown and same-file docstrings for exact entity-name mentions."""
    root = Path(root).resolve()
    md_docs = _collect_markdown(root)
    source_cache: Dict[str, str] = {}

    result = DocScan(doc_files=[rel for rel, _ in md_docs])
    for entity in entities:
        sources: List[str] = []

        md_hits = _mentioned_in_markdown(entity.entity_name, md_docs)
        sources.extend(md_hits)

        source = _source_for_file(root, entity.file, source_cache)
        if source and _mentioned_in_file_docstrings(entity.entity_name, source):
            sources.append(f"docstring:{entity.file}")

        if sources:
            result.mentions[entity.key] = sources

    return result


def scan_docs(root: str | Path, source_paths: Iterable[str]) -> DocScan:
    """Legacy file-level scan using the file stem as a pseudo entity name."""
    pseudo = [
        EntityInfo(
            entity_name=Path(src).stem,
            entity_type="file",
            file=src,
            start_line=1,
            end_line=1,
            loc=COMPLEX_ENTITY_MIN_LOC,
        )
        for src in source_paths
    ]
    raw = scan_entity_docs(root, pseudo)
    remapped = DocScan(doc_files=raw.doc_files)
    for entity in pseudo:
        if entity.key in raw.mentions:
            remapped.mentions[entity.file] = raw.mentions[entity.key]
    return remapped


# --------------------------------------------------------------------------- #
# Matching helpers
# --------------------------------------------------------------------------- #
def _entity_name_pattern(name: str) -> re.Pattern[str]:
    """Case-sensitive word-boundary pattern for an exact entity name."""
    return re.compile(r"\b" + re.escape(name) + r"\b")


def _collect_markdown(root: Path) -> List[tuple[str, str]]:
    """Return (relative path, original-case text) for every markdown file."""
    docs: List[tuple[str, str]] = []
    for path in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        text = _safe_read(path)
        if text is None:
            continue
        docs.append((path.relative_to(root).as_posix(), text))
    return docs


def _mentioned_in_markdown(name: str, docs: List[tuple[str, str]]) -> List[str]:
    """Markdown files where ``name`` appears as a whole word (exact case)."""
    if not name or name == "__init__":
        return []
    pattern = _entity_name_pattern(name)
    return [rel for rel, text in docs if pattern.search(text)]


def _mentioned_in_file_docstrings(name: str, source: str) -> bool:
    """True when ``name`` appears in any docstring in ``source``."""
    if not name or name == "__init__":
        return False
    pattern = _entity_name_pattern(name)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    module_doc = ast.get_docstring(tree)
    if module_doc and pattern.search(module_doc):
        return True

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        doc = ast.get_docstring(node)
        if doc and pattern.search(doc):
            return True
    return False


def _source_for_file(
    root: Path, rel: str, cache: Dict[str, str]
) -> Optional[str]:
    if rel not in cache:
        cache[rel] = _safe_read(root / rel) or ""
    return cache[rel] or None
