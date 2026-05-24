from src.schema import (
    Chunk,
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
