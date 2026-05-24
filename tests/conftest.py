"""Shared pytest fixtures and a deterministic fake embedding model.

The real SentenceTransformer downloads ~100MB of weights on first
use and needs network access - neither of which we want in unit
tests. `FakeEncoder` gives us reproducible vectors based on simple
hashed features, which is plenty for testing the surrounding plumbing
(shapes, normalization, ranking behavior, persistence).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Sequence

import numpy as np
import pytest

from src.config import DEFAULT_EMBEDDING_DIM, PipelineConfig
from src.embeddings import Embedder


class FakeEncoder:
    """Deterministic pseudo-encoder used in tests.

    It maps every input string to a fixed-dimensional vector derived
    from a stable hash of its tokens. That gives us two useful
    properties for testing:

    * The same string always encodes to the same vector.
    * Strings that share tokens end up closer in vector space than
      strings that don't - enough signal to assert on ranking order.
    """

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self.dim = dim
        self.calls: List[Sequence[str]] = []

    def encode(self, sentences, **_: object) -> np.ndarray:
        self.calls.append(list(sentences))
        vectors = np.zeros((len(sentences), self.dim), dtype=np.float32)
        for row, text in enumerate(sentences):
            for token in text.lower().split():
                bucket = int(hashlib.sha1(token.encode()).hexdigest(), 16) % self.dim
                vectors[row, bucket] += 1.0
            # Tiny constant so all-zero rows (empty strings) don't
            # collapse to NaN after normalization downstream.
            vectors[row, 0] += 1e-6
        return vectors


@pytest.fixture
def fake_encoder() -> FakeEncoder:
    return FakeEncoder()


@pytest.fixture
def embedder(fake_encoder: FakeEncoder) -> Embedder:
    """An Embedder wired to the deterministic fake - no network needed."""
    return Embedder(
        config=PipelineConfig.default(),
        model=fake_encoder,
    )


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """A tiny fake repo on disk that exercises every ingestion path."""
    repo = tmp_path / "sample_repo"
    repo.mkdir()
    (repo / "README.md").write_text(
        "# Sample\nThis project demonstrates caching behaviour for tests.\n",
        encoding="utf-8",
    )
    (repo / "cache.py").write_text(
        '"""Caching module."""\n\n'
        "def get(key):\n"
        '    """Return cached value for key."""\n'
        "    # look up the key in the cache\n"
        "    return _store.get(key)\n\n"
        "_store = {}\n",
        encoding="utf-8",
    )
    nested = repo / "utils"
    nested.mkdir()
    (nested / "helpers.py").write_text(
        "def add(a, b):\n"
        "    # trivial helper\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    # Noise we should NOT pick up.
    (repo / "notes.txt").write_text("ignored", encoding="utf-8")
    skipdir = repo / "__pycache__"
    skipdir.mkdir()
    (skipdir / "cache.cpython-311.pyc").write_bytes(b"bytecode")
    return repo
