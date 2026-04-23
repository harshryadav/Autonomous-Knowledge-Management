"""Repo ingestion: turn a folder of files into Documents.

The baseline only needs README + code + comments (per
PROJECT_PLAN.md), so that's all we extract here. The module
deliberately stays small - richer extraction (full AST entities,
commit history, ADRs) lands later as additional `load_*` helpers
that still return `Document` objects.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Iterable, List, Optional

from src.config import PipelineConfig
from src.schema import (
    Document,
    TYPE_CODE,
    TYPE_COMMENT,
    TYPE_DOCSTRING,
    TYPE_README,
)

log = logging.getLogger(__name__)

# Matches `# ...` comments but ignores shebangs and `# type:` hints
# that carry no semantic value for retrieval.
_INLINE_COMMENT_RE = re.compile(r"#\s?(.+)")
_SKIP_COMMENT_PREFIXES = ("!", "type:", "noqa", "pylint:", "pragma:")


def load_repo(
    repo_path: str | Path,
    config: Optional[PipelineConfig] = None,
) -> List[Document]:
    """Walk `repo_path` and return every Document we care about.

    Order of results is stable (sorted paths) so downstream chunk
    indices stay reproducible across runs - handy when debugging
    retrieval quality.
    """
    config = config or PipelineConfig.default()
    root = Path(repo_path)
    if not root.exists():
        raise FileNotFoundError(f"Repo path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repo path must be a directory: {root}")

    documents: List[Document] = []
    documents.extend(_load_readmes(root, config))
    documents.extend(_load_code_and_comments(root, config))
    log.info("Loaded %d documents from %s", len(documents), root)
    return documents


def _load_readmes(root: Path, config: PipelineConfig) -> List[Document]:
    """Pick up any README variant at the repo root."""
    docs: List[Document] = []
    for name in config.readme_names:
        path = root / name
        text = _safe_read_text(path, config.max_file_bytes)
        if text is None:
            continue
        docs.append(
            Document(
                type=TYPE_README,
                content=text,
                file=str(path.relative_to(root)),
            )
        )
    return docs


def _load_code_and_comments(
    root: Path, config: PipelineConfig
) -> List[Document]:
    """Recursively pull code files + extract their comments/docstrings."""
    docs: List[Document] = []
    for path in _iter_code_files(root, config.code_extensions):
        rel = str(path.relative_to(root))
        source = _safe_read_text(path, config.max_file_bytes)
        if source is None:
            continue

        docs.append(
            Document(
                type=TYPE_CODE,
                content=source,
                file=rel,
            )
        )

        # Comments and docstrings are where architectural "why" often
        # hides, so we surface them as first-class retrievable docs.
        if path.suffix == ".py":
            docs.extend(extract_python_comments(source, rel))
            docs.extend(extract_python_docstrings(source, rel))

    return docs


def _iter_code_files(root: Path, extensions: Iterable[str]) -> List[Path]:
    """All source files under root, sorted, skipping common noise dirs."""
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}
    results: List[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix in tuple(extensions):
            results.append(path)
    return results


def extract_python_comments(source: str, file: str) -> List[Document]:
    """Pull `#` comments out of a Python source string.

    We intentionally drop linter pragmas and shebangs - they're noise
    for semantic search.
    """
    comments: List[Document] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        match = _INLINE_COMMENT_RE.search(line)
        if not match:
            continue
        text = match.group(1).strip()
        if not text or text.startswith(_SKIP_COMMENT_PREFIXES):
            continue
        comments.append(
            Document(
                type=TYPE_COMMENT,
                content=text,
                file=file,
                start_line=lineno,
                end_line=lineno,
            )
        )
    return comments


def extract_python_docstrings(source: str, file: str) -> List[Document]:
    """Extract module / class / function docstrings via AST.

    Each docstring becomes its own Document so it can be embedded
    independently - functions with docstrings are prime Q&A targets.
    Parse errors are swallowed (returning what we have so far) because
    ingestion should never break on one broken file.
    """
    docs: List[Document] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        log.warning("Could not parse %s: %s", file, exc)
        return docs

    module_doc = ast.get_docstring(tree)
    if module_doc:
        docs.append(
            Document(
                type=TYPE_DOCSTRING,
                content=module_doc,
                file=file,
                function="<module>",
            )
        )

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        doc = ast.get_docstring(node)
        if not doc:
            continue
        docs.append(
            Document(
                type=TYPE_DOCSTRING,
                content=doc,
                file=file,
                function=node.name,
                start_line=getattr(node, "lineno", None),
                end_line=getattr(node, "end_lineno", None),
            )
        )
    return docs


def _safe_read_text(path: Path, max_bytes: int) -> Optional[str]:
    """Read text, or None if file missing / too big / undecodable.

    Returning None rather than raising keeps ingestion resilient: one
    bad file shouldn't kill the whole pipeline.
    """
    try:
        if not path.exists() or not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            log.warning("Skipping %s (>%d bytes)", path, max_bytes)
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None
