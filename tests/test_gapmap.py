"""End-to-end and unit tests for the GapMap CLI pipeline."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from gapmap.analysis import analyze
from gapmap.doc_scanner import scan_docs
from gapmap.generator import build_adr, write_adr
from gapmap.graph_builder import build_graph
from gapmap.parser import scan_repo
from gapmap.report import build_html
from gapmap.risk_engine import compute_risks, risk_level


@pytest.fixture()
def risky_repo(tmp_path: Path) -> Path:
    """A repo where `core.py` is load-bearing and undocumented."""
    (tmp_path / "core.py").write_text(
        textwrap.dedent(
            '''
            """Core routing logic."""

            def route(x):
                return x * 2

            def audit():
                return []
            '''
        ).strip()
    )
    (tmp_path / "a.py").write_text("import core\n\nprint(core.route(1))\n")
    (tmp_path / "b.py").write_text("from core import route\n\nroute(2)\n")
    (tmp_path / "lonely.py").write_text("X = 1\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("# Notes\n\nThe lonely module is unused.\n")
    return tmp_path


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def test_parser_finds_files_and_local_deps(risky_repo):
    modules = scan_repo(risky_repo)
    assert set(modules) == {"core.py", "a.py", "b.py", "lonely.py"}
    assert modules["a.py"].local_deps == ["core.py"]
    assert modules["b.py"].local_deps == ["core.py"]  # from-import resolves too
    assert modules["core.py"].local_deps == []
    assert modules["core.py"].loc > 0


def test_parser_resolves_package_imports(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text("VALUE = 1\n")
    (tmp_path / "user.py").write_text("from pkg.mod import VALUE\n")
    modules = scan_repo(tmp_path)
    assert "pkg/mod.py" in modules["user.py"].local_deps


def test_parser_skips_noise_dirs(tmp_path):
    (tmp_path / "real.py").write_text("X = 1\n")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "junk.py").write_text("Y = 2\n")
    assert set(scan_repo(tmp_path)) == {"real.py"}


# --------------------------------------------------------------------------- #
# Graph + risk
# --------------------------------------------------------------------------- #
def test_risk_score_is_incoming_times_loc(risky_repo):
    modules = scan_repo(risky_repo)
    graph = build_graph(modules)
    risks = {r.path: r for r in compute_risks(graph)}

    core = risks["core.py"]
    assert core.incoming == 2
    assert core.score == 2 * core.loc
    assert risks["lonely.py"].score == 0


def test_risks_sorted_highest_first(risky_repo):
    analysis = analyze(risky_repo)
    scores = [r.score for r in analysis.risks]
    assert scores == sorted(scores, reverse=True)
    assert analysis.risks[0].path == "core.py"


def test_risk_level_buckets():
    assert risk_level(100, 100) == "high"
    assert risk_level(20, 100) == "medium"
    assert risk_level(5, 100) == "low"
    assert risk_level(0, 100) == "low"
    assert risk_level(0, 0) == "low"


# --------------------------------------------------------------------------- #
# Doc scanner
# --------------------------------------------------------------------------- #
def test_doc_scanner_matches_on_word_boundary(risky_repo):
    scan = scan_docs(risky_repo, ["core.py", "a.py", "lonely.py"])
    assert scan.is_documented("lonely.py")        # "lonely" appears in notes.md
    assert not scan.is_documented("core.py")      # never mentioned
    assert not scan.is_documented("a.py")         # "a" alone must not match


def test_undocumented_risks_excludes_documented_and_zero_score(risky_repo):
    analysis = analyze(risky_repo)
    gaps = [r.path for r in analysis.undocumented_risks()]
    assert gaps == ["core.py"]


# --------------------------------------------------------------------------- #
# Ask + ADR + report
# --------------------------------------------------------------------------- #
def test_ask_answer_is_grounded(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from gapmap.ask import build_answer

    analysis = analyze(risky_repo)
    answer = build_answer(analysis, "core.py", "why is this risky?")
    assert "#1" in answer
    assert "2 incoming dependencies" in answer
    assert "No documentation" in answer


def test_adr_contains_required_sections(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    analysis = analyze(risky_repo)
    adr = build_adr(analysis, "core.py")
    for heading in (
        "## Context",
        "## Inferred Decision",
        "## Systemic Role",
        "## Trade-offs",
        "## Risks",
        "## Recommended Human Review",
    ):
        assert heading in adr
    assert "a.py" in adr and "b.py" in adr


def test_write_adr_creates_docs_file(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    analysis = analyze(risky_repo)
    out = write_adr(analysis, "core.py")
    assert out == risky_repo / "docs" / "core_ADR.md"
    assert out.exists()

    # After writing the ADR, a re-scan sees core.py as documented.
    assert analyze(risky_repo).is_documented("core.py")


def test_report_html_mentions_gaps(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    html = build_html(analyze(risky_repo))
    assert "core.py" in html
    assert "GapMap" in html
    assert "<!DOCTYPE html>" in html


# --------------------------------------------------------------------------- #
# Target resolution
# --------------------------------------------------------------------------- #
def test_resolve_target_by_basename_and_stem(risky_repo):
    analysis = analyze(risky_repo)
    assert analysis.resolve_target("core.py") == "core.py"
    assert analysis.resolve_target("core") == "core.py"
    assert analysis.resolve_target("missing.py") is None
