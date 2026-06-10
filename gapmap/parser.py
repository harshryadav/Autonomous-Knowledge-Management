"""Phase 2 - Code parser.

Scans a repository's Python files and extracts, per file:

- path (relative to the repo root)
- lines of code (non-blank)
- imported module names
- *local* dependencies, i.e. imports resolved to other files in the
  same repository
- **entities** — top-level class and function definitions parsed with
  tree-sitter, including per-entity LOC and outgoing calls to other
  local entities

``scan_entities()`` returns a unified dict of every entity in the repo,
keyed as ``"<file>::<entity_name>"``.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

log = logging.getLogger(__name__)

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
    "build",
    "dist",
}

MAX_FILE_BYTES = 1_000_000

ENTITY_CLASS = "class"
ENTITY_FUNCTION = "function"


@dataclass
class EntityInfo:
    """A top-level class or function extracted from one file."""

    entity_name: str
    entity_type: str          # "class" or "function"
    file: str                 # relative posix path
    start_line: int           # 1-indexed, inclusive
    end_line: int             # 1-indexed, inclusive
    loc: int                  # non-blank lines inside [start_line, end_line]
    outgoing_calls: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return entity_key(self.file, self.entity_name)

    def to_dict(self) -> dict:
        return {
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "loc": self.loc,
            "outgoing_calls": list(self.outgoing_calls),
        }


@dataclass
class ModuleInfo:
    """Everything the rest of GapMap needs to know about one file."""

    path: str
    loc: int
    imports: List[str] = field(default_factory=list)
    local_deps: List[str] = field(default_factory=list)
    entities: List[EntityInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "loc": self.loc,
            "imports": list(self.imports),
            "local_deps": list(self.local_deps),
            "entities": [e.to_dict() for e in self.entities],
        }


def entity_key(file: str, entity_name: str) -> str:
    """Stable id for the unified entity registry."""
    return f"{file}::{entity_name}"


def scan_repo(root: str | Path) -> Dict[str, ModuleInfo]:
    """Parse every Python file under ``root``.

    Returns a mapping of relative path -> ModuleInfo. Each ModuleInfo
    includes an ``entities`` list for that file. Use ``scan_entities``
    for a single flat registry across the whole codebase.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    files = _iter_python_files(root)
    index = _module_index(files)

    # Pass 1: read sources and extract entity shells (no outgoing calls yet).
    pending: List[Tuple[str, str, List[Tuple[str, str, object]]]] = []
    # Each item: (rel, source, [(name, type, ts_node), ...])
    all_names: Set[str] = set()

    for rel in files:
        source = _safe_read(root / rel)
        if source is None:
            continue
        raw_entities = _extract_entity_nodes(source, rel)
        for name, etype, _node in raw_entities:
            all_names.add(name)
        pending.append((rel, source, raw_entities))

    modules: Dict[str, ModuleInfo] = {}
    for rel, source, raw_entities in pending:
        loc = _count_non_blank_lines(source)
        imports = _extract_imports(source, rel)
        local_deps = _resolve_local(imports, index, rel)
        entities = _finalize_entities(source, rel, raw_entities, all_names)
        modules[rel] = ModuleInfo(
            path=rel,
            loc=loc,
            imports=imports,
            local_deps=local_deps,
            entities=entities,
        )

    log.info(
        "Scanned %d Python files (%d entities) in %s",
        len(modules),
        sum(len(m.entities) for m in modules.values()),
        root,
    )
    return modules


def scan_entities(root: str | Path) -> Dict[str, EntityInfo]:
    """Unified registry of every top-level entity across the codebase.

    Keys are ``"<relative/path.py>::<EntityName>"``.
    """
    entities: Dict[str, EntityInfo] = {}
    for module in scan_repo(root).values():
        for entity in module.entities:
            entities[entity.key] = entity
    return entities


# --------------------------------------------------------------------------- #
# tree-sitter
# --------------------------------------------------------------------------- #
_PARSER = None


def _get_parser():
    """Lazy-init the tree-sitter Python parser."""
    global _PARSER
    if _PARSER is None:
        import tree_sitter_python
        from tree_sitter import Language, Parser

        _PARSER = Parser(Language(tree_sitter_python.language()))
    return _PARSER


def _extract_entity_nodes(
    source: str, rel: str
) -> List[Tuple[str, str, object]]:
    """Return (name, entity_type, tree_sitter_node) for top-level entities."""
    try:
        tree = _get_parser().parse(source.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - unexpected TS failure
        log.warning("tree-sitter could not parse %s: %s", rel, exc)
        return []

    root = tree.root_node
    if root.has_error:
        log.warning("tree-sitter parse tree has errors in %s", rel)

    results: List[Tuple[str, str, object]] = []
    for child in root.children:
        node = child
        if child.type == "decorated_definition":
            node = _definition_under_decorator(child)
            if node is None:
                continue
        if node.type == "class_definition":
            name = _node_name(node)
            if name:
                results.append((name, ENTITY_CLASS, node))
        elif node.type == "function_definition":
            name = _node_name(node)
            if name:
                results.append((name, ENTITY_FUNCTION, node))
    return results


def _definition_under_decorator(node) -> Optional[object]:
    for child in node.children:
        if child.type in ("class_definition", "function_definition"):
            return child
    return None


def _node_name(node) -> Optional[str]:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    return name_node.text.decode("utf-8")


def _finalize_entities(
    source: str,
    rel: str,
    raw_entities: List[Tuple[str, str, object]],
    all_names: Set[str],
) -> List[EntityInfo]:
    """Turn raw tree-sitter nodes into EntityInfo with LOC and calls."""
    lines = source.splitlines()
    entities: List[EntityInfo] = []
    for name, etype, node in raw_entities:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        loc = _count_non_blank_lines_in_range(lines, start_line, end_line)
        outgoing = _extract_outgoing_calls(node, all_names)
        entities.append(
            EntityInfo(
                entity_name=name,
                entity_type=etype,
                file=rel,
                start_line=start_line,
                end_line=end_line,
                loc=loc,
                outgoing_calls=outgoing,
            )
        )
    return entities


def _extract_outgoing_calls(node, local_names: Set[str]) -> List[str]:
    """Find calls/instantiations of other local entities inside ``node``."""
    seen: Dict[str, None] = {}
    for desc in _walk(node):
        if desc.type != "call":
            continue
        func = desc.child_by_field_name("function")
        if func is None:
            continue
        target = _call_target_name(func)
        if target and target in local_names:
            seen.setdefault(target)
    return sorted(seen)


def _call_target_name(func_node) -> Optional[str]:
    """Resolve the callee name from a call's function expression."""
    if func_node.type == "identifier":
        return func_node.text.decode("utf-8")
    if func_node.type == "attribute":
        attr = func_node.child_by_field_name("attribute")
        if attr is not None:
            return attr.text.decode("utf-8")
    return None


def _walk(node):
    """Depth-first traversal of tree-sitter descendants."""
    stack = list(reversed(node.children))
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


# --------------------------------------------------------------------------- #
# File / import helpers (unchanged behaviour)
# --------------------------------------------------------------------------- #
def _iter_python_files(root: Path) -> List[str]:
    results = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        results.append(path.relative_to(root).as_posix())
    return results


def _module_index(files: List[str]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for rel in files:
        parts = rel[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            index[".".join(parts)] = rel
    return index


def _extract_imports(source: str, rel: str) -> List[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        log.warning("Could not parse %s: %s", rel, exc)
        return []

    package_parts = rel[:-3].split("/")[:-1]
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                anchor = package_parts[: len(package_parts) - (node.level - 1)]
                base = ".".join(anchor + ([node.module] if node.module else []))
            if base:
                names.append(base)
                for alias in node.names:
                    if alias.name != "*":
                        names.append(f"{base}.{alias.name}")
            else:
                for alias in node.names:
                    if alias.name != "*":
                        names.append(alias.name)

    seen: Dict[str, None] = {}
    for n in names:
        seen.setdefault(n)
    return list(seen)


def _resolve_local(
    imports: List[str], index: Dict[str, str], importer: str
) -> List[str]:
    deps: Dict[str, None] = {}
    for name in imports:
        target = _match(name, index)
        if target and target != importer:
            deps.setdefault(target)
    return list(deps)


def _match(name: str, index: Dict[str, str]) -> Optional[str]:
    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in index:
            return index[candidate]
        parts = parts[:-1]
    return None


def _count_non_blank_lines(source: str) -> int:
    return sum(1 for line in source.splitlines() if line.strip())


def _count_non_blank_lines_in_range(
    lines: List[str], start_line: int, end_line: int
) -> int:
    """Count non-blank lines in a 1-indexed inclusive range."""
    start = max(start_line - 1, 0)
    end = min(end_line, len(lines))
    return sum(1 for line in lines[start:end] if line.strip())


def _safe_read(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            log.warning("Skipping %s (too large)", path)
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None
