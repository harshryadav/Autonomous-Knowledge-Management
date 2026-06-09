"""Phase 2 - Code parser.

Scans a repository's Python files and extracts, per file:

- path (relative to the repo root)
- lines of code (non-blank)
- imported module names
- *local* dependencies, i.e. imports resolved to other files in the
  same repository ("checkout.py imports payment_router.py")

Resolution is static and best-effort: we map every file to its dotted
module name (``pkg/mod.py`` -> ``pkg.mod``) and match imports against
that index, trying progressively shorter prefixes so that
``from payments.router import route`` still resolves to
``payments/router.py``.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

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


@dataclass
class ModuleInfo:
    """Everything the rest of GapMap needs to know about one file."""

    path: str                                # relative posix path
    loc: int                                 # non-blank lines of code
    imports: List[str] = field(default_factory=list)      # raw dotted names
    local_deps: List[str] = field(default_factory=list)   # resolved repo paths

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "loc": self.loc,
            "imports": list(self.imports),
            "local_deps": list(self.local_deps),
        }


def scan_repo(root: str | Path) -> Dict[str, ModuleInfo]:
    """Parse every Python file under ``root``.

    Returns a mapping of relative path -> ModuleInfo. Files that fail
    to read or parse are skipped (with a warning) rather than aborting
    the whole scan - one broken file should never kill an audit.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    files = _iter_python_files(root)
    index = _module_index(files)

    modules: Dict[str, ModuleInfo] = {}
    for rel in files:
        source = _safe_read(root / rel)
        if source is None:
            continue
        loc = sum(1 for line in source.splitlines() if line.strip())
        imports = _extract_imports(source, rel)
        local_deps = _resolve_local(imports, index, rel)
        modules[rel] = ModuleInfo(
            path=rel, loc=loc, imports=imports, local_deps=local_deps
        )

    log.info("Scanned %d Python files in %s", len(modules), root)
    return modules


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _iter_python_files(root: Path) -> List[str]:
    results = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        results.append(path.relative_to(root).as_posix())
    return results


def _module_index(files: List[str]) -> Dict[str, str]:
    """Dotted module name -> relative file path.

    ``pkg/mod.py`` -> ``pkg.mod`` and ``pkg/__init__.py`` -> ``pkg``.
    """
    index: Dict[str, str] = {}
    for rel in files:
        parts = rel[:-3].split("/")  # strip ".py"
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            index[".".join(parts)] = rel
    return index


def _extract_imports(source: str, rel: str) -> List[str]:
    """Pull dotted module names from import statements.

    Relative imports (``from . import x``, ``from ..pkg import y``) are
    resolved against the importing file's package so they can be
    matched in the module index.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        log.warning("Could not parse %s: %s", rel, exc)
        return []

    package_parts = rel[:-3].split("/")[:-1]  # directories above the file

    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                # `from ..pkg import x`: climb `level` packages up.
                anchor = package_parts[: len(package_parts) - (node.level - 1)]
                base = ".".join(anchor + ([node.module] if node.module else []))
            if base:
                names.append(base)
                # `from base import name` may target a submodule file,
                # so also record base.name candidates for resolution.
                for alias in node.names:
                    if alias.name != "*":
                        names.append(f"{base}.{alias.name}")
            else:
                for alias in node.names:
                    if alias.name != "*":
                        names.append(alias.name)

    # De-duplicate, keep first-seen order.
    seen: Dict[str, None] = {}
    for n in names:
        seen.setdefault(n)
    return list(seen)


def _resolve_local(
    imports: List[str], index: Dict[str, str], importer: str
) -> List[str]:
    """Match imported names against repo files, longest prefix first."""
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


def _safe_read(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            log.warning("Skipping %s (too large)", path)
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None
