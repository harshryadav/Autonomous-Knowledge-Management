"""Phase 5 - Documentation scanner.

Finds every Markdown doc in the repo (docs/, adr/, README.md, any
*.md) and checks which source files are actually *mentioned* in them.
A risky file nobody wrote about is a documentation gap.

"Mentioned" = the file name (payment_router.py) or its stem
(payment_router) appears in a doc, matched on word boundaries so that
`auth` does not count as documentation for `auth_session.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

from gapmap.parser import SKIP_DIRS, _safe_read


@dataclass
class DocScan:
    doc_files: List[str] = field(default_factory=list)       # relative paths
    mentions: Dict[str, List[str]] = field(default_factory=dict)
    # mentions: source file path -> doc files that reference it

    def is_documented(self, path: str) -> bool:
        return bool(self.mentions.get(path))


def scan_docs(root: str | Path, source_paths: Iterable[str]) -> DocScan:
    """Scan all Markdown files and record which source files they mention."""
    root = Path(root).resolve()
    docs: List[tuple[str, str]] = []  # (relative path, lowercased text)
    for path in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        text = _safe_read(path)
        if text is None:
            continue
        docs.append((path.relative_to(root).as_posix(), text.lower()))

    result = DocScan(doc_files=[rel for rel, _ in docs])
    for src in source_paths:
        stem = Path(src).stem.lower()
        if stem == "__init__":
            # Match the package directory name instead of "__init__".
            parts = Path(src).parts
            stem = parts[-2].lower() if len(parts) > 1 else stem
        pattern = re.compile(r"\b" + re.escape(stem) + r"\b")
        hits = [rel for rel, text in docs if pattern.search(text)]
        if hits:
            result.mentions[src] = hits
    return result
