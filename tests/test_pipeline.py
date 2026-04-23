import pytest

from src.pipeline import Pipeline
from src.retrieval import Retriever


def test_build_then_query_returns_relevant_chunks(sample_repo, embedder):
    pipeline = Pipeline(embedder=embedder)
    pipeline.build(sample_repo)

    results = pipeline.query("caching value for key", k=3)
    assert results, "expected at least one hit"
    # The cache.py docstring or comment should be among the top hits.
    files = {r.chunk.file for r in results}
    assert "cache.py" in files


def test_build_returns_chunks(sample_repo, embedder):
    pipeline = Pipeline(embedder=embedder)
    chunks = pipeline.build(sample_repo)
    assert chunks, "pipeline should produce chunks from the sample repo"
    # We should have a mix of types - proof the whole chain ran.
    types = {c.type for c in chunks}
    assert {"readme", "code"}.issubset(types)


def test_query_rejects_empty_string(sample_repo, embedder):
    pipeline = Pipeline(embedder=embedder)
    pipeline.build(sample_repo)
    with pytest.raises(ValueError):
        pipeline.query("   ")


def test_build_on_empty_repo_is_noop(tmp_path, embedder):
    pipeline = Pipeline(embedder=embedder)
    chunks = pipeline.build(tmp_path)
    assert chunks == []
    assert pipeline.retriever.size == 0


def test_save_and_load_pipeline_roundtrip(sample_repo, embedder, tmp_path):
    pipeline = Pipeline(embedder=embedder)
    pipeline.build(sample_repo)
    pipeline.save(tmp_path / "index")

    reloaded = Pipeline.load(tmp_path / "index", embedder=embedder)
    assert isinstance(reloaded.retriever, Retriever)
    assert reloaded.retriever.size == pipeline.retriever.size

    # Querying the reloaded pipeline should still work.
    results = reloaded.query("caching", k=2)
    assert results
