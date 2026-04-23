import numpy as np
import pytest

from src.retrieval import Retriever
from src.schema import Chunk, TYPE_CODE, TYPE_README

DIM = 4  # tiny dim keeps these tests readable


def _chunks(n: int):
    return [Chunk(content=f"c{i}", type=TYPE_CODE, file=f"f{i}.py") for i in range(n)]


def _unit(vec):
    v = np.array(vec, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_empty_retriever_returns_empty_list():
    r = Retriever(dim=DIM)
    results = r.search(np.zeros((1, DIM), dtype=np.float32), k=3)
    assert results == []


def test_add_and_search_returns_closest_chunk_first():
    r = Retriever(dim=DIM)
    # f0: far from query, f1: perfect match, f2: partial match - gives an
    # unambiguous ordering (no tie-breaking by insertion order).
    vectors = np.vstack(
        [_unit([1, 0, 0, 0]), _unit([0, 1, 0, 0]), _unit([0, 1, 1, 0])]
    )
    chunks = _chunks(3)
    r.add(vectors, chunks)

    query = _unit([0, 1, 0, 0]).reshape(1, -1)
    results = r.search(query, k=2)
    assert [res.chunk.file for res in results] == ["f1.py", "f2.py"]
    assert results[0].score == pytest.approx(1.0, abs=1e-5)
    assert results[0].rank == 0
    assert results[1].rank == 1


def test_search_caps_k_at_index_size():
    r = Retriever(dim=DIM)
    r.add(np.eye(2, DIM, dtype=np.float32), _chunks(2))
    results = r.search(_unit([1, 0, 0, 0]).reshape(1, -1), k=50)
    assert len(results) == 2


def test_add_rejects_mismatched_lengths():
    r = Retriever(dim=DIM)
    with pytest.raises(ValueError):
        r.add(np.zeros((3, DIM), dtype=np.float32), _chunks(2))


def test_add_rejects_wrong_dim():
    r = Retriever(dim=DIM)
    with pytest.raises(ValueError):
        r.add(np.zeros((2, DIM + 1), dtype=np.float32), _chunks(2))


def test_search_accepts_1d_query():
    r = Retriever(dim=DIM)
    r.add(np.eye(2, DIM, dtype=np.float32), _chunks(2))
    results = r.search(_unit([1, 0, 0, 0]), k=1)
    assert len(results) == 1


def test_search_rejects_multi_row_query():
    r = Retriever(dim=DIM)
    r.add(np.eye(2, DIM, dtype=np.float32), _chunks(2))
    with pytest.raises(ValueError):
        r.search(np.eye(2, DIM, dtype=np.float32), k=1)


def test_search_batch_returns_per_query_results():
    r = Retriever(dim=DIM)
    r.add(np.eye(3, DIM, dtype=np.float32), _chunks(3))
    queries = np.vstack([_unit([1, 0, 0, 0]), _unit([0, 0, 1, 0])])
    batches = r.search_batch(queries, k=1)
    assert [b[0].chunk.file for b in batches] == ["f0.py", "f2.py"]


def test_save_and_load_roundtrip(tmp_path):
    r = Retriever(dim=DIM)
    vectors = np.eye(3, DIM, dtype=np.float32)
    chunks = [
        Chunk(content="readme text", type=TYPE_README, file="README.md"),
        Chunk(content="code a", type=TYPE_CODE, file="a.py", function="foo", start_line=1, end_line=5),
        Chunk(content="code b", type=TYPE_CODE, file="b.py"),
    ]
    r.add(vectors, chunks)
    r.save(tmp_path)

    reloaded = Retriever.load(tmp_path)
    assert reloaded.size == 3
    results = reloaded.search(_unit([0, 1, 0, 0]).reshape(1, -1), k=1)
    assert results[0].chunk.file == "a.py"
    assert results[0].chunk.function == "foo"
