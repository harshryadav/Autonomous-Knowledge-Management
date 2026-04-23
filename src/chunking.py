"""Chunking strategies.

We split prose and code differently:

* Prose (README, docstrings, comments) is split by *words* with an
  overlap window. Overlap matters: otherwise a sentence that falls
  on a boundary loses context and its embedding gets noisy.
* Code is split by *lines* so we don't shred function bodies across
  meaningless word boundaries.

Small chunks (< size) are passed through as-is instead of being
padded - embeddings of tiny text are still perfectly valid.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from src.config import PipelineConfig
from src.schema import Chunk, Document, TYPE_CODE


def chunk_documents(
    documents: Iterable[Document],
    config: Optional[PipelineConfig] = None,
) -> List[Chunk]:
    """Turn Documents into retrieval-ready Chunks."""
    config = config or PipelineConfig.default()
    chunks: List[Chunk] = []
    for doc in documents:
        if not doc.content or not doc.content.strip():
            # Empty files (touch'd placeholders) happen - skip them.
            continue
        if doc.type == TYPE_CODE:
            chunks.extend(
                _chunk_by_lines(
                    doc,
                    size=config.code_chunk_size,
                    overlap=config.code_chunk_overlap,
                )
            )
        else:
            chunks.extend(
                _chunk_by_words(
                    doc,
                    size=config.prose_chunk_size,
                    overlap=config.prose_chunk_overlap,
                )
            )
    return chunks


def _chunk_by_words(doc: Document, size: int, overlap: int) -> List[Chunk]:
    """Sliding-window word chunker with overlap for prose-like content."""
    _validate_window(size, overlap)
    words = doc.content.split()
    if not words:
        return []
    if len(words) <= size:
        return [Chunk.from_document(doc, doc.content, chunk_index=0)]

    step = size - overlap
    chunks: List[Chunk] = []
    for idx, start in enumerate(range(0, len(words), step)):
        window = words[start : start + size]
        if not window:
            break
        chunks.append(
            Chunk.from_document(doc, " ".join(window), chunk_index=idx)
        )
        if start + size >= len(words):
            break
    return chunks


def _chunk_by_lines(doc: Document, size: int, overlap: int) -> List[Chunk]:
    """Sliding-window line chunker for code.

    Line numbers are tracked so a retrieved chunk can point the reader
    back to the exact region of the file - essential later when we
    start building the "why was this designed this way" answers.
    """
    _validate_window(size, overlap)
    lines = doc.content.splitlines()
    if not lines:
        return []
    if len(lines) <= size:
        return [
            Chunk.from_document(
                doc,
                doc.content,
                chunk_index=0,
                start_line=1,
                end_line=len(lines),
            )
        ]

    step = size - overlap
    chunks: List[Chunk] = []
    for idx, start in enumerate(range(0, len(lines), step)):
        window = lines[start : start + size]
        if not window:
            break
        chunks.append(
            Chunk.from_document(
                doc,
                "\n".join(window),
                chunk_index=idx,
                start_line=start + 1,
                end_line=start + len(window),
            )
        )
        if start + size >= len(lines):
            break
    return chunks


def _validate_window(size: int, overlap: int) -> None:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if overlap < 0:
        raise ValueError("chunk overlap must be non-negative")
    if overlap >= size:
        # Without this guard the sliding window would never advance.
        raise ValueError("chunk overlap must be smaller than chunk size")
