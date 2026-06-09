"""Phase 7 - Risk Q&A.

`gapmap ask payment_router.py "why is this risky?"`

The answer is grounded exclusively in facts the pipeline measured:
risk score and rank, incoming/outgoing dependencies, documentation
status, and a structural summary of the source itself. If an OpenAI
key is configured the same facts are handed to a model for a more
fluent write-up; otherwise a deterministic template is used.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from gapmap.analysis import RepoAnalysis
from gapmap.llm import maybe_complete
from gapmap.risk_engine import risk_level


@dataclass
class CodeSummary:
    docstring: Optional[str] = None
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)


def summarize_source(root: Path, rel: str) -> CodeSummary:
    """Top-level structure of a file: docstring, classes, functions."""
    summary = CodeSummary()
    try:
        source = (root / rel).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return summary
    doc = ast.get_docstring(tree)
    if doc:
        summary.docstring = doc.strip().splitlines()[0]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            summary.classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            summary.functions.append(node.name)
    return summary


def build_answer(analysis: RepoAnalysis, path: str, question: str) -> str:
    """Answer a question about a file using only measured facts."""
    risk = analysis.risk_for(path)
    if risk is None:
        return f"{path} was not found in the scanned repository."

    rank = analysis.rank_of(path)
    importers = analysis.importers_of(path)
    dependencies = analysis.dependencies_of(path)
    documented = analysis.is_documented(path)
    doc_hits = analysis.docs.mentions.get(path, [])
    level = risk_level(risk.score, analysis.max_score())
    summary = summarize_source(analysis.root, path)

    facts = _facts_block(
        path, risk, rank, level, importers, dependencies,
        documented, doc_hits, summary,
    )

    llm_answer = maybe_complete(
        system=(
            "You are GapMap, a code-risk analyst. Answer the developer's "
            "question using ONLY the facts provided. Be concise and concrete. "
            "Do not invent dependencies, scores, or documentation that are "
            "not listed in the facts."
        ),
        user=f"Question about {path}: {question}\n\nFacts:\n{facts}",
    )
    if llm_answer:
        return llm_answer

    return _template_answer(
        path, risk, rank, level, importers, dependencies,
        documented, doc_hits, summary,
    )


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _facts_block(path, risk, rank, level, importers, dependencies,
                 documented, doc_hits, summary) -> str:
    lines = [
        f"file: {path}",
        f"risk_score: {risk.score} (incoming {risk.incoming} x LOC {risk.loc})",
        f"risk_rank: {'unranked' if rank is None else f'#{rank}'}",
        f"risk_level: {level}",
        f"imported_by ({risk.incoming}): {', '.join(importers) or 'none'}",
        f"imports ({risk.outgoing}): {', '.join(dependencies) or 'none'}",
        f"documented: {'yes - ' + ', '.join(doc_hits) if documented else 'no'}",
    ]
    if summary.docstring:
        lines.append(f"module_docstring: {summary.docstring}")
    if summary.classes:
        lines.append(f"classes: {', '.join(summary.classes)}")
    if summary.functions:
        lines.append(f"functions: {', '.join(summary.functions)}")
    return "\n".join(lines)


def _template_answer(path, risk, rank, level, importers, dependencies,
                     documented, doc_hits, summary) -> str:
    name = Path(path).name
    parts: List[str] = []

    if risk.incoming == 0:
        parts.append(
            f"{name} currently has a risk score of 0: no other file in the "
            f"repository imports it, so changes to it have a limited blast "
            f"radius."
        )
    else:
        parts.append(
            f"{name} is the #{rank} risk in this repository with a risk "
            f"score of {risk.score} ({level} risk). The score is "
            f"{risk.incoming} incoming dependencies x {risk.loc} lines of "
            f"code."
        )
        shown = ", ".join(importers[:8])
        more = f" (+{len(importers) - 8} more)" if len(importers) > 8 else ""
        parts.append(
            f"It is load-bearing: {risk.incoming} file(s) depend on it - "
            f"{shown}{more}. A breaking change here propagates to all of "
            f"them."
        )

    if dependencies:
        parts.append(
            f"It depends on {risk.outgoing} local file(s): "
            f"{', '.join(dependencies[:8])}."
        )

    if documented:
        parts.append(
            f"Documentation exists: it is mentioned in "
            f"{', '.join(doc_hits)}."
        )
    else:
        parts.append(
            "No documentation mentions this file - there is no README, ADR, "
            "or design doc explaining why it works the way it does. The "
            "knowledge lives only in the code (and whoever wrote it)."
        )

    structure = []
    if summary.docstring:
        structure.append(f'describes itself as "{summary.docstring}"')
    if summary.classes:
        structure.append(f"defines class(es) {', '.join(summary.classes)}")
    if summary.functions:
        count = len(summary.functions)
        structure.append(
            f"exposes {count} top-level function(s) "
            f"({', '.join(summary.functions[:6])}{'...' if count > 6 else ''})"
        )
    if structure:
        parts.append(f"Structurally, {name} {'; '.join(structure)}.")

    if risk.incoming > 0 and not documented:
        parts.append(
            "Recommendation: this is exactly the kind of file to document "
            f"first. Run `gapmap generate {name}` to draft an ADR."
        )
    return "\n\n".join(parts)
