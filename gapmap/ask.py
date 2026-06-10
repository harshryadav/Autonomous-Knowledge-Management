"""Phase 7 - Risk Q&A.

`gapmap ask route_payment "why is this risky?"`

Answers are grounded in entity-level facts: risk score, in/out degree,
documentation status, and source structure.
"""

from __future__ import annotations

from typing import List, Optional

from gapmap.analysis import RepoAnalysis
from gapmap.llm import maybe_complete
from gapmap.risk_engine import risk_level


def build_answer(analysis: RepoAnalysis, key: str, question: str) -> str:
    """Answer a question about an entity using only measured facts."""
    risk = analysis.risk_for(key)
    if risk is None:
        return f"{key} was not found in the scanned repository."

    entity = analysis.entities.get(key)
    rank = analysis.rank_of(key)
    importers = analysis.importers_of(key)
    dependencies = analysis.dependencies_of(key)
    documented = analysis.is_documented(key)
    doc_hits = analysis.docs.mentions.get(key, [])
    level = risk_level(risk.score, analysis.max_score())
    label = f"{risk.entity_name} ({risk.entity_type} in {risk.file})"

    facts = _facts_block(
        risk, label, rank, level, importers, dependencies,
        documented, doc_hits, entity,
    )

    llm_answer = maybe_complete(
        system=(
            "You are GapMap, a code-risk analyst. Answer the developer's "
            "question using ONLY the facts provided. Be concise and concrete. "
            "Do not invent dependencies, scores, or documentation that are "
            "not listed in the facts."
        ),
        user=f"Question about {label}: {question}\n\nFacts:\n{facts}",
    )
    if llm_answer:
        return llm_answer

    return _template_answer(
        risk, label, rank, level, importers, dependencies,
        documented, doc_hits, entity,
    )


def _facts_block(risk, label, rank, level, importers, dependencies,
                 documented, doc_hits, entity) -> str:
    lines = [
        f"entity: {label}",
        f"risk_score: {risk.score} (in-degree {risk.incoming} x LOC {risk.loc})",
        f"risk_rank: {'unranked' if rank is None else f'#{rank}'}",
        f"risk_level: {level}",
        f"called_by ({risk.incoming}): {', '.join(importers) or 'none'}",
        f"calls ({risk.outgoing}): {', '.join(dependencies) or 'none'}",
        f"documented: {'yes - ' + ', '.join(doc_hits) if documented else 'no'}",
    ]
    if entity is not None:
        lines.append(f"lines: {entity.start_line}-{entity.end_line}")
    return "\n".join(lines)


def _template_answer(risk, label, rank, level, importers, dependencies,
                     documented, doc_hits, entity) -> str:
    parts: List[str] = []

    if risk.incoming == 0:
        parts.append(
            f"{risk.entity_name} currently has a risk score of 0: no other "
            f"entity in the repository calls or instantiates it, so changes "
            f"have a limited blast radius."
        )
    else:
        parts.append(
            f"{label} is the #{rank} risk in this repository with a score "
            f"of {risk.score} ({level} risk). The score is "
            f"{risk.incoming} incoming callers x {risk.loc} lines of code "
            f"in this {risk.entity_type}."
        )
        shown = ", ".join(importers[:8])
        more = f" (+{len(importers) - 8} more)" if len(importers) > 8 else ""
        parts.append(
            f"It is load-bearing: {risk.incoming} entity/entities depend on "
            f"it - {shown}{more}. A breaking change here propagates through "
            f"the call graph."
        )

    if dependencies:
        parts.append(
            f"It calls or instantiates {risk.outgoing} other local "
            f"entity/entities: {', '.join(dependencies[:8])}."
        )

    if documented:
        parts.append(
            f"Documentation exists: mentioned in {', '.join(doc_hits)}."
        )
    else:
        parts.append(
            "No documentation mentions this entity or its module - there is "
            "no README, ADR, or design doc explaining why it works this way."
        )

    if entity is not None:
        parts.append(
            f"Located at {risk.file} lines {entity.start_line}-{entity.end_line}."
        )

    if risk.incoming > 0 and not documented:
        parts.append(
            "Recommendation: document this entity first. Run "
            f"`gapmap generate {risk.entity_name}` to draft an ADR."
        )
    return "\n\n".join(parts)
