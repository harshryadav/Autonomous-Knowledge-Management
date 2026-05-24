"""End-to-end pipeline orchestration.

This is the one place that stitches ingestion -> chunking ->
embedding -> indexing together. Everything else stays unaware of
anything outside its own layer, which keeps the system easy to test
and easy to extend: later work (graph expansion, LLM-backed answer
synthesis, gap detection) can layer on top without touching the
lower stages.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from src.chunking import chunk_documents
from src.config import PipelineConfig
from src.embeddings import Embedder
from src.ingestion import load_repo
from src.retrieval import Retriever, RetrievalResult
from src.schema import Chunk

log = logging.getLogger(__name__)


class Pipeline:
    """High-level 'build index, answer queries' facade."""

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        embedder: Optional[Embedder] = None,
        retriever: Optional[Retriever] = None,
    ) -> None:
        self.config = config or PipelineConfig.default()
        self.embedder = embedder or Embedder(self.config)
        self.retriever = retriever or Retriever(dim=self.config.embedding_dim)

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #
    def build(self, repo_path: str | Path) -> List[Chunk]:
        """Ingest a repo and populate the retriever. Returns the chunks.

        Returning chunks (rather than keeping them purely internal) is
        useful for notebooks and for downstream layers (entity
        extraction, graph construction) that want to iterate the same
        chunks without re-running ingestion.
        """
        log.info("Building pipeline from %s", repo_path)
        documents = load_repo(repo_path, self.config)
        chunks = chunk_documents(documents, self.config)
        if not chunks:
            log.warning("No chunks produced for %s", repo_path)
            return []

        embeddings = self.embedder.embed_chunks(chunks)
        self.retriever.add(embeddings, chunks)
        log.info("Indexed %d chunks", len(chunks))
        return chunks

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #
    def query(
        self, text: str, k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """Encode `text` and return the top matching chunks."""
        if not text or not text.strip():
            raise ValueError("query text must be non-empty")
        k = k if k is not None else self.config.top_k
        query_vec = self.embedder.encode([text])
        return self.retriever.search(query_vec, k=k)

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, directory: str | Path) -> None:
        """Write the retriever state so we don't have to re-embed later."""
        self.retriever.save(directory)

    @classmethod
    def load(
        cls,
        directory: str | Path,
        config: Optional[PipelineConfig] = None,
        embedder: Optional[Embedder] = None,
    ) -> "Pipeline":
        """Rebuild a Pipeline from a previously-saved index."""
        config = config or PipelineConfig.default()
        retriever = Retriever.load(directory)
        return cls(config=config, embedder=embedder, retriever=retriever)
