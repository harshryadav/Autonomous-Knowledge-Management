"""Unit tests for the answer-synthesis (Q&A) layer.

Every test runs offline and deterministically: we inject fake LLM
clients rather than calling a real model. The fakes also let us assert
on the *prompt* the synthesizer builds, which is where the grounding
and prompt-injection-isolation guarantees live.
"""

from __future__ import annotations

from typing import List

import pytest

from src.config import PipelineConfig
from src.qa import (
    AnswerSynthesizer,
    ExtractiveLLM,
    SYSTEM_PROMPT,
    _CONTEXT_CLOSE,
    _CONTEXT_OPEN,
)
from src.retrieval import RetrievalResult
from src.schema import Chunk, TYPE_CODE, TYPE_COMMENT


# --------------------------------------------------------------------------- #
# Test doubles + builders
# --------------------------------------------------------------------------- #
class RecordingLLM:
    """Fake LLM that records the prompts it received and returns canned text."""

    def __init__(self, reply: str = "Caching is used in cache.py [1].") -> None:
        self.reply = reply
        self.system_prompts: List[str] = []
        self.user_prompts: List[str] = []

    def complete(self, system: str, user: str) -> str:
        self.system_prompts.append(system)
        self.user_prompts.append(user)
        return self.reply


class BoomLLM:
    """Fake LLM that always fails - exercises the runtime fallback path."""

    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("simulated provider outage")


def _result(content: str, file: str, score: float, **kw) -> RetrievalResult:
    chunk = Chunk(content=content, type=kw.pop("type", TYPE_CODE), file=file, **kw)
    return RetrievalResult(chunk=chunk, score=score, rank=0)


def _results() -> List[RetrievalResult]:
    return [
        _result("def get(key): return _store.get(key)", "cache.py", 0.82, function="get"),
        _result("look up the key in the cache", "cache.py", 0.55, type=TYPE_COMMENT, start_line=9),
    ]


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_synthesize_returns_grounded_answer_with_citations():
    llm = RecordingLLM()
    synth = AnswerSynthesizer(llm=llm)

    answer = synth.synthesize("Where is caching used?", _results())

    assert answer.text == "Caching is used in cache.py [1]."
    assert answer.strategy == "llm"
    assert answer.query == "Where is caching used?"
    assert len(answer.citations) == 2
    # Confidence is the mean of the used source scores.
    assert answer.confidence == pytest.approx((0.82 + 0.55) / 2)


def test_citation_markers_are_one_indexed_and_aligned():
    llm = RecordingLLM()
    synth = AnswerSynthesizer(llm=llm)

    answer = synth.synthesize("q", _results())

    markers = [c.marker for c in answer.citations]
    assert markers == [1, 2]
    # The same markers must appear in the prompt the model saw.
    prompt = llm.user_prompts[0]
    assert "[1]" in prompt and "[2]" in prompt


# --------------------------------------------------------------------------- #
# Prompt construction / injection isolation
# --------------------------------------------------------------------------- #
def test_context_is_fenced_and_system_prompt_warns_about_untrusted_data():
    llm = RecordingLLM()
    synth = AnswerSynthesizer(llm=llm)
    synth.synthesize("q", _results())

    user = llm.user_prompts[0]
    assert _CONTEXT_OPEN in user and _CONTEXT_CLOSE in user
    # The actual retrieved content lands inside the fence.
    assert "_store.get(key)" in user
    # System prompt must instruct the model to treat context as data.
    assert "untrusted" in SYSTEM_PROMPT.lower()


def test_context_respects_char_budget():
    cfg = PipelineConfig.default()
    cfg.answer_max_context_chars = 30  # only the first source fits
    cfg.answer_min_score = 0.0
    llm = RecordingLLM()
    synth = AnswerSynthesizer(config=cfg, llm=llm)

    answer = synth.synthesize("q", _results())
    # Budget is tiny, so only one source should be packed/cited.
    assert len(answer.citations) == 1


# --------------------------------------------------------------------------- #
# Confidence gating / refusal
# --------------------------------------------------------------------------- #
def test_low_scoring_results_trigger_refusal():
    cfg = PipelineConfig.default()
    cfg.answer_min_score = 0.9  # nothing clears the bar
    synth = AnswerSynthesizer(config=cfg, llm=RecordingLLM())

    answer = synth.synthesize("q", _results())
    assert answer.strategy == "refused"
    assert answer.citations == []
    assert answer.confidence == 0.0
    assert "enough information" in answer.text.lower()


def test_empty_results_refuses():
    synth = AnswerSynthesizer(llm=RecordingLLM())
    answer = synth.synthesize("q", [])
    assert answer.strategy == "refused"


def test_empty_query_raises():
    synth = AnswerSynthesizer(llm=RecordingLLM())
    with pytest.raises(ValueError):
        synth.synthesize("   ", _results())


# --------------------------------------------------------------------------- #
# Fallback behavior
# --------------------------------------------------------------------------- #
def test_runtime_llm_failure_degrades_to_extractive():
    synth = AnswerSynthesizer(llm=BoomLLM())
    answer = synth.synthesize("q", _results())

    assert answer.strategy == "extractive-fallback"
    # Falls back to quoting the sources rather than failing the request.
    assert "_store.get(key)" in answer.text
    assert answer.citations  # citations still attached


def test_loader_failure_falls_back_to_extractive_engine():
    def broken_loader(_config):
        raise ImportError("openai not installed")

    synth = AnswerSynthesizer(llm_loader=broken_loader)
    # Resolving .llm should not raise; it degrades to ExtractiveLLM.
    assert isinstance(synth.llm, ExtractiveLLM)

    answer = synth.synthesize("q", _results())
    assert answer.strategy == "extractive"
    assert "_store.get(key)" in answer.text


def test_extractive_llm_handles_missing_context():
    # Defensive: a malformed prompt with no fence yields a safe message.
    out = ExtractiveLLM().complete("sys", "no context here")
    assert "don't have enough information" in out.lower()


# --------------------------------------------------------------------------- #
# Pipeline integration
# --------------------------------------------------------------------------- #
def test_pipeline_answer_end_to_end(sample_repo, embedder):
    from src.pipeline import Pipeline

    synth = AnswerSynthesizer(llm=RecordingLLM(reply="It demonstrates caching [1]."))
    pipeline = Pipeline(embedder=embedder, synthesizer=synth)
    pipeline.build(sample_repo)

    answer = pipeline.answer("What does this repo do?", k=4)
    assert answer.text
    assert answer.strategy in {"llm", "extractive", "extractive-fallback", "refused"}


def test_pipeline_answer_rejects_empty_query(sample_repo, embedder):
    from src.pipeline import Pipeline

    pipeline = Pipeline(embedder=embedder, synthesizer=AnswerSynthesizer(llm=RecordingLLM()))
    pipeline.build(sample_repo)
    with pytest.raises(ValueError):
        pipeline.answer("  ")
