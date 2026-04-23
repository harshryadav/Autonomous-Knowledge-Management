"""FAISS-backed vector retriever.

Uses `IndexFlatIP` on L2-normalized vectors, which gives cosine
similarity scores in [-1, 1]. That's both the most intuitive metric
for semantic search and the one that plays nicely with how we're
normalizing in `embeddings.py`.

We keep the index fully in-memory - fine for up to a few hundred
thousand chunks. Swap to `IndexIVFFlat` or a hosted vector DB once
we push past ~1M vectors.
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from src.config import DEFAULT_EMBEDDING_DIM
from src.schema import Chunk

log = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """One hit from a retriever.search() call."""

    chunk: Chunk
    score: float          # cosine similarity, higher is better
    rank: int             # 0-indexed position in the result list

    def to_dict(self) -> Dict[str, Any]:
        out = self.chunk.to_dict()
        out["score"] = float(self.score)
        out["rank"] = int(self.rank)
        return out


class Retriever:
    """Thin FAISS wrapper that remembers which Chunk each vector came from."""

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        # Import inside __init__ so the module is importable even in
        # environments where FAISS isn't installed (e.g. doc generation).
        import faiss  # noqa: WPS433

        self._faiss = faiss
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.chunks: List[Chunk] = []

    # ------------------------------------------------------------------ #
    # Index building
    # ------------------------------------------------------------------ #
    def add(self, embeddings: np.ndarray, chunks: Sequence[Chunk]) -> None:
        """Store `embeddings` alongside their source Chunks.

        Shapes must line up: `embeddings.shape[0] == len(chunks)`.
        """
        if len(chunks) == 0:
            return
        vectors = _ensure_matrix(embeddings, self.dim)
        if vectors.shape[0] != len(chunks):
            raise ValueError(
                f"embeddings/chunks length mismatch: "
                f"{vectors.shape[0]} vs {len(chunks)}"
            )
        self.index.add(vectors)
        self.chunks.extend(chunks)

    # ------------------------------------------------------------------ #
    # Querying
    # ------------------------------------------------------------------ #
    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 5,
    ) -> List[RetrievalResult]:
        """Return top-k most similar Chunks for a single query vector."""
        if self.size == 0:
            return []
        if k <= 0:
            raise ValueError("k must be positive")

        matrix = _ensure_matrix(query_embedding, self.dim)
        if matrix.shape[0] != 1:
            raise ValueError(
                "search() expects exactly one query embedding; "
                "use search_batch() for multiple"
            )

        effective_k = min(k, self.size)
        scores, indices = self.index.search(matrix, effective_k)
        return self._build_results(scores[0], indices[0])

    def search_batch(
        self,
        query_embeddings: np.ndarray,
        k: int = 5,
    ) -> List[List[RetrievalResult]]:
        """Vectorized search for multiple queries at once."""
        if self.size == 0:
            return [[] for _ in range(len(query_embeddings))]
        matrix = _ensure_matrix(query_embeddings, self.dim)
        effective_k = min(k, self.size)
        scores, indices = self.index.search(matrix, effective_k)
        return [
            self._build_results(scores[row], indices[row])
            for row in range(matrix.shape[0])
        ]

    def _build_results(
        self, scores: np.ndarray, indices: np.ndarray
    ) -> List[RetrievalResult]:
        results: List[RetrievalResult] = []
        for rank, (score, idx) in enumerate(zip(scores, indices)):
            # FAISS returns -1 when it has fewer items than k requested.
            if idx == -1:
                continue
            results.append(
                RetrievalResult(
                    chunk=self.chunks[int(idx)],
                    score=float(score),
                    rank=rank,
                )
            )
        return results

    # ------------------------------------------------------------------ #
    # Introspection + persistence
    # ------------------------------------------------------------------ #
    @property
    def size(self) -> int:
        return int(self.index.ntotal)

    def save(self, directory: str | Path) -> None:
        """Persist the FAISS index + chunk metadata to disk.

        Metadata goes out as JSON (human-inspectable) while the FAISS
        index uses its native binary format.
        """
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        self._faiss.write_index(self.index, str(path / "index.faiss"))
        with open(path / "chunks.json", "w", encoding="utf-8") as fh:
            json.dump([c.to_dict() for c in self.chunks], fh, indent=2)
        with open(path / "meta.pkl", "wb") as fh:
            pickle.dump({"dim": self.dim}, fh)

    @classmethod
    def load(cls, directory: str | Path) -> "Retriever":
        """Reload a Retriever previously written by `.save()`."""
        import faiss  # noqa: WPS433

        path = Path(directory)
        with open(path / "meta.pkl", "rb") as fh:
            meta = pickle.load(fh)
        retriever = cls(dim=meta["dim"])
        retriever.index = faiss.read_index(str(path / "index.faiss"))
        with open(path / "chunks.json", "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        retriever.chunks = [Chunk(**c) for c in raw]
        return retriever


def _ensure_matrix(vectors: np.ndarray, dim: int) -> np.ndarray:
    """Coerce input to a contiguous (N, dim) float32 array.

    FAISS is picky about dtype and contiguity; centralizing this
    conversion means callers never need to care.
    """
    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2:
        raise ValueError(f"expected 1D or 2D input, got shape {arr.shape}")
    if arr.shape[1] != dim:
        raise ValueError(
            f"embedding dim mismatch: expected {dim}, got {arr.shape[1]}"
        )
    return np.ascontiguousarray(arr)
