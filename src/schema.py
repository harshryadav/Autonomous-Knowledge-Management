"""Shared data schema for the knowledge pipeline.

This is the contract between the extraction side (ingestion, AST
parsing, future entity extraction) and the retrieval side. Whatever
source we pull from (README, source code, commit message, ADR later
on), it eventually lands as a `Chunk` so the retriever can treat
every piece of knowledge uniformly.

The JSON shape mirrors the integration schema in PROJECT_PLAN.md:

    {"type": "comment", "content": "...", "file": "x.py", "function": "foo"}
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


# Canonical values for the `type` field. Keeping these centralized so
# both sides of the pipeline agree on spelling (no "readme" vs "README"
# drift two weeks from now).
TYPE_README = "readme"
TYPE_CODE = "code"
TYPE_COMMENT = "comment"
TYPE_DOCSTRING = "docstring"

VALID_TYPES = frozenset({TYPE_README, TYPE_CODE, TYPE_COMMENT, TYPE_DOCSTRING})


@dataclass
class Document:
    """A raw piece of text pulled from a repository before chunking.

    Think of this as "one file-or-entity's worth" of content. Chunking
    turns a Document into one or more Chunks.
    """

    type: str
    content: str
    file: str
    function: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in VALID_TYPES:
            # Not fatal - we allow unknown types so new extractors can
            # experiment - but we warn loudly via the exception message
            # if someone passes something obviously wrong (empty string).
            if not self.type:
                raise ValueError("Document.type must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Chunk:
    """A retrieval-sized slice of a Document.

    `content` is what actually gets embedded. Everything else is
    metadata we carry around so answers can be cited back to their
    original location in the repo.
    """

    content: str
    type: str
    file: str
    function: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    chunk_index: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_document(
        cls,
        doc: Document,
        content: str,
        chunk_index: int = 0,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> "Chunk":
        """Build a Chunk that inherits metadata from its parent Document."""
        return cls(
            content=content,
            type=doc.type,
            file=doc.file,
            function=doc.function,
            start_line=start_line if start_line is not None else doc.start_line,
            end_line=end_line if end_line is not None else doc.end_line,
            chunk_index=chunk_index,
            extra=dict(doc.extra),
        )


@dataclass
class Citation:
    """A single source backing an answer.

    Answers must be *grounded*: every claim should trace back to a
    concrete location in the repo. A Citation is the minimal pointer
    needed to let a developer jump to that location and verify the
    answer themselves. We deliberately keep the source `content`
    around (not just the location) so the UI can render a snippet and
    so we can later score answer/source faithfulness offline.
    """

    marker: int          # 1-indexed [n] reference used inside answer text
    file: str
    type: str
    score: float         # retrieval similarity that surfaced this source
    function: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    content: str = ""

    def location(self) -> str:
        """Human-readable `file::function:Lstart` pointer for display/logs."""
        loc = self.file
        if self.function:
            loc += f"::{self.function}"
        if self.start_line is not None:
            loc += f":L{self.start_line}"
        return loc

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Answer:
    """The synthesized response to a developer question.

    This is the public contract of the intelligence layer: a natural
    language `text`, the `citations` that ground it, and enough
    metadata (`confidence`, `strategy`) for callers to decide how much
    to trust it and how to render it. Keeping this as a plain dataclass
    (rather than a bare string) means downstream consumers - a CLI, a
    web API, an evaluation harness - all speak the same language.
    """

    text: str
    citations: list = field(default_factory=list)  # list[Citation]
    confidence: float = 0.0           # 0..1, derived from retrieval scores
    strategy: str = "extractive"      # which synthesizer produced this
    query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "citations": [c.to_dict() for c in self.citations],
            "confidence": float(self.confidence),
            "strategy": self.strategy,
            "query": self.query,
        }
