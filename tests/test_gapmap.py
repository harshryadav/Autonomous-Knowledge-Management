"""End-to-end and unit tests for the GapMap CLI pipeline."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from gapmap.analysis import analyze
from gapmap.doc_scanner import COMPLEX_ENTITY_MIN_LOC, scan_docs, scan_entity_docs
from gapmap.generator import build_adr, extract_entity_source, generate_adr, write_adr
from gapmap.graph_builder import build_graph
from gapmap.parser import ENTITY_CLASS, ENTITY_FUNCTION, scan_entities, scan_repo
from gapmap.report import build_html
from gapmap.risk_engine import compute_risks, risk_level


@pytest.fixture()
def risky_repo(tmp_path: Path) -> Path:
    """A repo where ``core.py::route`` is load-bearing and undocumented."""
    (tmp_path / "core.py").write_text(
        textwrap.dedent(
            '''
            """Core routing logic."""

            def route(x):
                if x is None:
                    raise ValueError("x required")
                doubled = x * 2
                return doubled

            def audit():
                return []
            '''
        ).strip()
    )
    (tmp_path / "a.py").write_text(
        textwrap.dedent(
            '''
            import core

            def invoke():
                core.route(1)
            '''
        ).strip()
    )
    (tmp_path / "b.py").write_text(
        textwrap.dedent(
            '''
            from core import route

            def invoke():
                route(2)
            '''
        ).strip()
    )
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


def test_parser_extracts_top_level_entities(tmp_path):
    (tmp_path / "svc.py").write_text(
        textwrap.dedent(
            '''
            class PaymentRouter:
                def handle(self):
                    pass

            def process_refund():
                return 1
            '''
        ).strip()
    )
    modules = scan_repo(tmp_path)
    names = {e.entity_name: e for e in modules["svc.py"].entities}
    assert set(names) == {"PaymentRouter", "process_refund"}
    assert names["PaymentRouter"].entity_type == ENTITY_CLASS
    assert names["process_refund"].entity_type == ENTITY_FUNCTION
    assert names["PaymentRouter"].start_line == 1
    assert names["PaymentRouter"].loc >= 3
    assert names["process_refund"].end_line >= names["process_refund"].start_line


def test_parser_extracts_outgoing_calls_to_local_entities(tmp_path):
    (tmp_path / "core.py").write_text(
        textwrap.dedent(
            '''
            def helper():
                return 1

            def orchestrate():
                helper()
                return helper()
            '''
        ).strip()
    )
    entities = scan_entities(tmp_path)
    orch = entities["core.py::orchestrate"]
    assert orch.outgoing_calls == ["helper"]
    assert entities["core.py::helper"].outgoing_calls == []


def test_scan_entities_returns_unified_registry(tmp_path):
    (tmp_path / "a.py").write_text("class Alpha: pass\n")
    (tmp_path / "b.py").write_text("class Beta: pass\n")
    registry = scan_entities(tmp_path)
    assert set(registry) == {"a.py::Alpha", "b.py::Beta"}
    assert registry["a.py::Alpha"].file == "a.py"


def test_nested_methods_are_not_top_level_entities(tmp_path):
    (tmp_path / "mod.py").write_text(
        textwrap.dedent(
            '''
            class Service:
                def inner(self):
                    pass
            '''
        ).strip()
    )
    entities = scan_entities(tmp_path)
    assert list(entities) == ["mod.py::Service"]


def test_entity_graph_edges_follow_calls(tmp_path):
    (tmp_path / "core.py").write_text(
        "def helper():\n    return 1\n\ndef orchestrate():\n    helper()\n"
    )
    graph = build_graph(scan_repo(tmp_path))
    assert graph.has_edge("core.py::orchestrate", "core.py::helper")
    assert not graph.has_edge("core.py::helper", "core.py::orchestrate")


# --------------------------------------------------------------------------- #
# Graph + risk
# --------------------------------------------------------------------------- #
def test_risk_score_is_incoming_times_loc(risky_repo):
    modules = scan_repo(risky_repo)
    graph = build_graph(modules)
    risks = {r.key: r for r in compute_risks(graph)}

    route = risks["core.py::route"]
    assert route.incoming == 2
    assert route.score == 2 * route.loc
    assert risks["core.py::audit"].score == 0


def test_risks_sorted_highest_first(risky_repo):
    analysis = analyze(risky_repo)
    scores = [r.score for r in analysis.risks]
    assert scores == sorted(scores, reverse=True)
    assert analysis.risks[0].key == "core.py::route"


def test_risk_level_buckets():
    assert risk_level(100, 100) == "high"
    assert risk_level(20, 100) == "medium"
    assert risk_level(5, 100) == "low"
    assert risk_level(0, 100) == "low"
    assert risk_level(0, 0) == "low"


# --------------------------------------------------------------------------- #
# Doc scanner
# --------------------------------------------------------------------------- #
def test_doc_scanner_matches_entity_name_with_word_boundary(tmp_path):
    (tmp_path / "svc.py").write_text("class PaymentRouter:\n    pass\n")
    (tmp_path / "docs" / "guide.md").parent.mkdir(parents=True)
    (tmp_path / "docs" / "guide.md").write_text("# Payment routing\n\nSee PaymentRouter.\n")
    entities = list(scan_entities(tmp_path).values())
    scan = scan_entity_docs(tmp_path, entities)
    assert scan.is_documented("svc.py::PaymentRouter")
    assert "docs/guide.md" in scan.mentions["svc.py::PaymentRouter"]


def test_doc_scanner_does_not_match_file_stem_without_entity_name(risky_repo):
    analysis = analyze(risky_repo)
    assert not analysis.is_documented("core.py::route")
    # invoke is simple (low LOC) — undocumented but not flagged as a gap:
    assert not analysis.is_documented("a.py::invoke")
    assert not analysis.is_undocumented("a.py::invoke")


def test_doc_scanner_counts_same_file_docstring(tmp_path):
    (tmp_path / "mod.py").write_text(
        '"""Uses Helper for processing."""\n\nclass Helper:\n    """Helper docs."""\n    pass\n'
    )
    entities = list(scan_entities(tmp_path).values())
    scan = scan_entity_docs(tmp_path, entities)
    assert scan.is_documented("mod.py::Helper")


def test_doc_scanner_flags_complex_undocumented_entities(risky_repo):
    analysis = analyze(risky_repo)
    route = analysis.entities["core.py::route"]
    assert route.loc >= COMPLEX_ENTITY_MIN_LOC
    assert analysis.is_undocumented("core.py::route")
    # File-level legacy scan: "lonely" appears in notes.md
    scan = scan_docs(risky_repo, ["lonely.py"])
    assert scan.is_documented("lonely.py")


def test_undocumented_risks_excludes_documented_and_zero_score(risky_repo):
    analysis = analyze(risky_repo)
    gaps = [r.key for r in analysis.undocumented_risks()]
    assert gaps == ["core.py::route"]


# --------------------------------------------------------------------------- #
# Ask + ADR + report
# --------------------------------------------------------------------------- #
def test_ask_answer_is_grounded(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from gapmap.ask import build_answer

    analysis = analyze(risky_repo)
    answer = build_answer(analysis, "core.py::route", "why is this risky?")
    assert "#1" in answer
    assert "2 incoming callers" in answer
    assert "No documentation" in answer


def test_generate_adr_uses_entity_source_block_not_whole_file(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    analysis = analyze(risky_repo)
    entity = analysis.entities["core.py::route"]
    block = extract_entity_source(analysis, entity)
    adr = generate_adr(analysis, "core.py::route", source_block=block)

    assert "def route(x):" in adr
    assert "def audit():" not in adr
    assert "## Source Code" in adr
    assert "```python" in adr


def test_adr_contains_required_sections(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    analysis = analyze(risky_repo)
    adr = build_adr(analysis, "core.py::route")
    for heading in (
        "## Context",
        "## Inferred Decision",
        "## Architectural Responsibilities",
        "## Systemic Role",
        "## Trade-offs",
        "## Risks",
        "## Recommended Human Review",
    ):
        assert heading in adr
    assert "a.py::invoke" in adr and "b.py::invoke" in adr


def test_write_adr_creates_numbered_file_under_docs_adr(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    analysis = analyze(risky_repo)
    out = write_adr(analysis, "core.py::route")
    assert out.parent == risky_repo / "docs" / "adr"
    assert out.name == "001_route_ADR.md"
    assert out.exists()

    # After writing the ADR, a re-scan sees route as documented.
    assert analyze(risky_repo).is_documented("core.py::route")


def test_report_html_mentions_gaps(risky_repo, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    html = build_html(analyze(risky_repo))
    assert "route" in html
    assert "GapMap" in html
    assert "<!DOCTYPE html>" in html


# --------------------------------------------------------------------------- #
# Target resolution
# --------------------------------------------------------------------------- #
def test_resolve_target_by_basename_and_stem(risky_repo):
    analysis = analyze(risky_repo)
    assert analysis.resolve_target("core.py::route") == "core.py::route"
    assert analysis.resolve_target("route") == "core.py::route"
    assert analysis.resolve_target("core.py") == "core.py::route"
    assert analysis.resolve_target("missing.py") is None
