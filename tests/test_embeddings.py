import numpy as np
import pytest

from src.config import PipelineConfig
from src.embeddings import Embedder
from src.schema import Chunk, TYPE_CODE


def test_encode_returns_normalized_float32_matrix(embedder):
    vectors = embedder.encode(["hello world", "hello there"])
    assert vectors.shape == (2, PipelineConfig.default().embedding_dim)
    assert vectors.dtype == np.float32
    # Unit norm means every row sums (squared) to ~1.
    norms = np.linalg.norm(vectors, axis=1)
    np.testing.assert_allclose(norms, np.ones(2), atol=1e-5)


def test_encode_empty_returns_shaped_zero_matrix(embedder):
    vectors = embedder.encode([])
    assert vectors.shape == (0, PipelineConfig.default().embedding_dim)


def test_embed_chunks_matches_encode(embedder):
    chunks = [
        Chunk(content="cache logic", type=TYPE_CODE, file="a.py"),
        Chunk(content="trivial helper", type=TYPE_CODE, file="b.py"),
    ]
    via_chunks = embedder.embed_chunks(chunks)
    via_texts = embedder.encode([c.content for c in chunks])
    np.testing.assert_array_equal(via_chunks, via_texts)


def test_model_is_lazy_loaded():
    calls = []

    def fake_loader(name):
        calls.append(name)
        return type("Stub", (), {"encode": staticmethod(lambda xs, **_: np.ones((len(xs), PipelineConfig.default().embedding_dim), dtype=np.float32))})()

    emb = Embedder(model_loader=fake_loader)
    assert calls == []  # not loaded yet
    emb.encode(["hi"])
    assert calls == [PipelineConfig.default().model_name]
    # Second call should reuse the model.
    emb.encode(["again"])
    assert calls == [PipelineConfig.default().model_name]


def test_encode_rejects_non_2d_output():
    class BadModel:
        def encode(self, xs, **_):
            return np.zeros((len(xs),), dtype=np.float32)  # 1D by mistake

    emb = Embedder(model=BadModel())
    with pytest.raises(ValueError):
        emb.encode(["x"])


def test_similar_texts_rank_higher_than_unrelated(embedder):
    anchor = embedder.encode(["caching layer implementation"])
    similar = embedder.encode(["caching layer"])
    unrelated = embedder.encode(["totally different words"])
    # Cosine sim via dot product since vectors are unit-norm.
    sim_close = (anchor @ similar.T).item()
    sim_far = (anchor @ unrelated.T).item()
    assert sim_close > sim_far
