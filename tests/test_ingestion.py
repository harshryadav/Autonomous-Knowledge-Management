from pathlib import Path

import pytest

from src.ingestion import (
    extract_python_comments,
    extract_python_docstrings,
    load_repo,
)
from src.schema import (
    TYPE_CODE,
    TYPE_COMMENT,
    TYPE_DOCSTRING,
    TYPE_README,
)


def test_load_repo_returns_readme_code_comments_and_docstrings(sample_repo):
    docs = load_repo(sample_repo)
    by_type = {}
    for d in docs:
        by_type.setdefault(d.type, []).append(d)

    assert TYPE_README in by_type
    assert TYPE_CODE in by_type
    assert TYPE_COMMENT in by_type
    assert TYPE_DOCSTRING in by_type

    # Two Python files = two code docs (recursion works).
    code_files = {d.file for d in by_type[TYPE_CODE]}
    assert code_files == {"cache.py", "utils/helpers.py"}


def test_load_repo_skips_pycache_and_non_code(sample_repo):
    docs = load_repo(sample_repo)
    files = {d.file for d in docs}
    assert not any("__pycache__" in f for f in files)
    assert not any(f.endswith("notes.txt") for f in files)


def test_load_repo_raises_on_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_repo(tmp_path / "does-not-exist")


def test_load_repo_raises_when_path_is_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        load_repo(f)


def test_extract_python_comments_drops_pragmas_and_shebangs():
    source = (
        "#!/usr/bin/env python\n"
        "# real comment explaining intent\n"
        "x = 1  # type: ignore\n"
        "y = 2  # noqa: E501\n"
        "z = 3  # another real one\n"
    )
    comments = extract_python_comments(source, "a.py")
    contents = [c.content for c in comments]
    assert "real comment explaining intent" in contents
    assert "another real one" in contents
    assert not any("noqa" in c for c in contents)
    assert not any("type:" in c for c in contents)


def test_extract_python_comments_tracks_line_numbers():
    source = "x = 1\n# hello\n"
    comments = extract_python_comments(source, "a.py")
    assert len(comments) == 1
    assert comments[0].start_line == 2
    assert comments[0].end_line == 2


def test_extract_python_docstrings_captures_module_and_functions():
    source = (
        '"""Module doc."""\n'
        "def foo():\n"
        '    """Foo doc."""\n'
        "    return 1\n"
        "class Bar:\n"
        '    """Bar doc."""\n'
        "    pass\n"
    )
    docs = extract_python_docstrings(source, "a.py")
    by_fn = {d.function: d.content for d in docs}
    assert by_fn["<module>"] == "Module doc."
    assert by_fn["foo"] == "Foo doc."
    assert by_fn["Bar"] == "Bar doc."


def test_extract_python_docstrings_handles_syntax_error_gracefully():
    # Should not raise - resilience matters during ingestion.
    result = extract_python_docstrings("def (:\n", "broken.py")
    assert result == []


def test_load_repo_skips_oversized_files(tmp_path, monkeypatch):
    (tmp_path / "huge.py").write_text("x = 1\n" * 10, encoding="utf-8")
    from src.config import PipelineConfig

    cfg = PipelineConfig.default()
    cfg.max_file_bytes = 5  # absurdly small so the file is skipped
    docs = load_repo(tmp_path, cfg)
    assert not any(d.file == "huge.py" for d in docs)
