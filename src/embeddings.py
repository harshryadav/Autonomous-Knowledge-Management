"""Sentence-BERT embedding wrapper.

Two small-but-important design choices here:

1. **Lazy loading.** The model downloads weights the first time it's
   used, so we don't want that to happen at `import` time (which
   would make unit tests slow and require network access).
2. **L2-normalized output.** Pair this with a FAISS inner-product
   index and you get true cosine similarity, which is what you
   actually want for semantic search. Using plain L2 distance on
   un-normalized vectors (the previous baseline) gave scores that
   were hard to compare across queries.

The `Embedder` class accepts an injected `model_loader`, which makes
tests trivial: pass in a fake that returns deterministic vectors and
you never touch the network.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable, List, Optional, Protocol

import numpy as np

from src.config import PipelineConfig
from src.schema import Chunk

log = logging.getLogger(__name__)


class _EncoderLike(Protocol):
    """Minimal interface we rely on from SentenceTransformer.

    Declaring this as a Protocol means any duck-typed object (including
    the fakes used in tests) is accepted without us having to import
    sentence_transformers just for type checking.
    """

    def encode(self, sentences, **kwargs) -> np.ndarray: ...  # pragma: no cover


ModelLoader = Callable[[str], _EncoderLike]


def _default_model_loader(model_name: str) -> _EncoderLike:
    """Import sentence_transformers lazily so tests can skip it."""
    from sentence_transformers import SentenceTransformer  # noqa: WPS433

    return SentenceTransformer(model_name)


class Embedder:
    """Encodes text into L2-normalized float32 vectors."""

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        model: Optional[_EncoderLike] = None,
        model_loader: ModelLoader = _default_model_loader,
    ) -> None:
        self.config = config or PipelineConfig.default()
        self._model: Optional[_EncoderLike] = model
        self._model_loader = model_loader

    @property
    def model(self) -> _EncoderLike:
        """Load the underlying encoder on first access."""
        if self._model is None:
            log.info("Loading embedding model: %s", self.config.model_name)
            self._model = self._model_loader(self.config.model_name)
        return self._model

    def encode(self, texts: Iterable[str]) -> np.ndarray:
        """Encode an iterable of strings into a (N, dim) float32 matrix.

        Empty input returns an empty (0, dim) array so callers can
        concatenate results without worrying about shape mismatches.
        """
        texts_list: List[str] = list(texts)
        if not texts_list:
            return np.zeros((0, self.config.embedding_dim), dtype=np.float32)

        raw = self.model.encode(
            texts_list,
            batch_size=self.config.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        vectors = np.asarray(raw, dtype=np.float32)
        if vectors.ndim != 2:
            raise ValueError(
                f"Expected 2D embeddings, got shape {vectors.shape}"
            )
        return _l2_normalize(vectors)

    def embed_chunks(self, chunks: Iterable[Chunk]) -> np.ndarray:
        """Convenience wrapper for the common 'encode all Chunks' case."""
        return self.encode(c.content for c in chunks)


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """Divide each row by its L2 norm (safe on zero vectors)."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    # Replace zeros so we never divide by zero; a zero vector stays zero.
    norms = np.where(norms == 0, 1.0, norms)
    return (vectors / norms).astype(np.float32)
