import pytest

from src.chunking import chunk_documents
from src.config import PipelineConfig
from src.schema import Document, TYPE_CODE, TYPE_README


def test_short_prose_document_returns_single_chunk():
    doc = Document(type=TYPE_README, content="hello world", file="README.md")
    chunks = chunk_documents([doc])
    assert len(chunks) == 1
    assert chunks[0].content == "hello world"
    assert chunks[0].chunk_index == 0


def test_prose_chunking_overlaps_and_covers_all_words():
    words = [f"w{i}" for i in range(400)]
    doc = Document(type=TYPE_README, content=" ".join(words), file="README.md")
    cfg = PipelineConfig.default()
    cfg.prose_chunk_size = 100
    cfg.prose_chunk_overlap = 20
    chunks = chunk_documents([doc], cfg)

    # Every original word should appear in at least one chunk.
    seen = set()
    for c in chunks:
        seen.update(c.content.split())
    assert seen == set(words)

    # Consecutive chunks should share overlap (20 words).
    first_tail = chunks[0].content.split()[-20:]
    second_head = chunks[1].content.split()[:20]
    assert first_tail == second_head


def test_code_chunking_preserves_line_numbers():
    lines = [f"line {i}" for i in range(100)]
    doc = Document(type=TYPE_CODE, content="\n".join(lines), file="a.py")
    cfg = PipelineConfig.default()
    cfg.code_chunk_size = 30
    cfg.code_chunk_overlap = 5
    chunks = chunk_documents([doc], cfg)

    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 30
    # Second chunk should start at step = size - overlap = 25.
    assert chunks[1].start_line == 26


def test_empty_documents_are_dropped():
    docs = [
        Document(type=TYPE_README, content="", file="a.md"),
        Document(type=TYPE_README, content="   \n\t", file="b.md"),
    ]
    assert chunk_documents(docs) == []


def test_invalid_window_raises():
    doc = Document(type=TYPE_README, content="a b c", file="r.md")
    cfg = PipelineConfig.default()
    cfg.prose_chunk_size = 10
    cfg.prose_chunk_overlap = 10
    with pytest.raises(ValueError):
        chunk_documents([doc], cfg)
