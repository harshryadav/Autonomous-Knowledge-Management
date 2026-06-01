from src.schema import (
    Answer,
    Chunk,
    Citation,
    Document,
    TYPE_CODE,
    TYPE_README,
    VALID_TYPES,
)


def test_document_rejects_empty_type():
    import pytest

    with pytest.raises(ValueError):
        Document(type="", content="x", file="f.py")


def test_document_to_dict_roundtrip():
    doc = Document(
        type=TYPE_README,
        content="hi",
        file="README.md",
        function=None,
        extra={"tag": "root"},
    )
    payload = doc.to_dict()
    assert payload["type"] == TYPE_README
    assert payload["file"] == "README.md"
    assert payload["extra"] == {"tag": "root"}


def test_chunk_from_document_inherits_metadata():
    doc = Document(type=TYPE_CODE, content="x", file="a.py", function="foo")
    chunk = Chunk.from_document(doc, content="abc", chunk_index=2)
    assert chunk.file == "a.py"
    assert chunk.function == "foo"
    assert chunk.chunk_index == 2
    assert chunk.type == TYPE_CODE


def test_valid_types_are_distinct():
    assert len(VALID_TYPES) >= 4


def test_citation_location_formats_file_function_and_line():
    c = Citation(
        marker=1, file="cache.py", type=TYPE_CODE, score=0.8,
        function="get", start_line=9,
    )
    assert c.location() == "cache.py::get:L9"


def test_citation_location_handles_missing_metadata():
    c = Citation(marker=1, file="README.md", type=TYPE_README, score=0.5)
    assert c.location() == "README.md"


def test_answer_to_dict_serializes_citations():
    c = Citation(marker=1, file="a.py", type=TYPE_CODE, score=0.9, content="x")
    ans = Answer(text="hi [1]", citations=[c], confidence=0.9, strategy="llm", query="q")
    payload = ans.to_dict()
    assert payload["text"] == "hi [1]"
    assert payload["citations"][0]["marker"] == 1
    assert payload["confidence"] == 0.9
    assert payload["strategy"] == "llm"
