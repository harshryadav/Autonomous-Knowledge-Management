"""Phase 8 - ADR generator.

`gapmap generate payment_router.py` writes
`docs/payment_router_ADR.md` with the sections the implementation plan
requires: Context, Inferred Decision, Systemic Role, Trade-offs,
Risks, and Recommended Human Review.

Every section is grounded in measured facts (graph degrees, LOC, doc
scan, AST structure). With an OpenAI key set, the same facts are
rewritten more fluently by a model; the structure and the "draft -
needs human review" framing are identical either way.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List

from gapmap.analysis import RepoAnalysis
from gapmap.ask import summarize_source
from gapmap.llm import maybe_complete
from gapmap.risk_engine import risk_level


def adr_path_for(analysis: RepoAnalysis, path: str) -> Path:
    return analysis.root / "docs" / f"{Path(path).stem}_ADR.md"


def build_adr(analysis: RepoAnalysis, path: str) -> str:
    """Render the ADR markdown for one file."""
    risk = analysis.risk_for(path)
    if risk is None:
        raise ValueError(f"{path} not found in the scanned repository")

    rank = analysis.rank_of(path)
    importers = analysis.importers_of(path)
    dependencies = analysis.dependencies_of(path)
    documented = analysis.is_documented(path)
    level = risk_level(risk.score, analysis.max_score())
    summary = summarize_source(analysis.root, path)
    name = Path(path).name

    context = _context_section(name, risk, rank, level, documented, summary)
    decision = _decision_section(name, risk, importers, dependencies, summary)
    role = _role_section(name, importers, dependencies)
    tradeoffs = _tradeoffs_section(name, risk)
    risks = _risks_section(name, risk, documented)
    review = _review_section(name)

    body = _assemble(
        name, context, decision, role, tradeoffs, risks, review
    )

    polished = maybe_complete(
        system=(
            "You are GapMap, drafting an Architecture Decision Record. "
            "Rewrite the draft ADR below so it reads naturally, keeping the "
            "exact same markdown section headings, all factual claims, and "
            "the 'draft / needs human review' framing. Do not add facts."
        ),
        user=body,
    )
    return polished or body


def write_adr(analysis: RepoAnalysis, path: str) -> Path:
    """Generate and save the ADR. Returns the output path."""
    output = adr_path_for(analysis, path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_adr(analysis, path), encoding="utf-8")
    return output


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def _context_section(name, risk, rank, level, documented, summary) -> str:
    lines = [
        f"`{name}` is ranked **#{rank}** by risk in this repository "
        f"(risk score **{risk.score}** = {risk.incoming} incoming "
        f"dependencies x {risk.loc} lines of code, {level} risk).",
    ]
    if summary.docstring:
        lines.append(f'Its module docstring describes it as: "{summary.docstring}".')
    if documented:
        lines.append("Some documentation already mentions this file.")
    else:
        lines.append(
            "No existing documentation (README, ADRs, design docs) mentions "
            "this file, so this record was generated to close that gap."
        )
    return "\n\n".join(lines)


def _decision_section(name, risk, importers, dependencies, summary) -> str:
    shape: List[str] = []
    if summary.classes:
        shape.append(f"class(es) `{'`, `'.join(summary.classes)}`")
    if summary.functions:
        shape.append(f"{len(summary.functions)} top-level function(s)")
    shape_text = " and ".join(shape) if shape else "its current structure"

    return (
        f"The codebase centralizes this responsibility in a single module: "
        f"{len(importers)} file(s) route through `{name}` ({shape_text}) "
        f"instead of implementing the logic locally. This is an *inferred* "
        f"decision reconstructed from the dependency structure - the "
        f"original rationale was not written down and should be confirmed "
        f"by the authors."
    )


def _role_section(name, importers, dependencies) -> str:
    lines = []
    if importers:
        lines.append("**Depended on by:**")
        lines.extend(f"- `{imp}`" for imp in importers)
    else:
        lines.append("No files currently depend on this module.")
    if dependencies:
        lines.append("")
        lines.append("**Depends on:**")
        lines.extend(f"- `{dep}`" for dep in dependencies)
    return "\n".join(lines)


def _tradeoffs_section(name, risk) -> str:
    return "\n".join([
        f"- **Centralization vs. blast radius.** Routing {risk.incoming} "
        f"caller(s) through one module avoids duplication, but any breaking "
        f"change here affects all of them at once.",
        f"- **Size vs. reviewability.** At {risk.loc} lines, changes are "
        f"harder to review and the module likely mixes several concerns.",
        "- **Implicit contract.** Callers rely on behavior that is defined "
        "only by the implementation, not by documented guarantees.",
    ])


def _risks_section(name, risk, documented) -> str:
    items = [
        f"- Single point of failure: a regression in `{name}` propagates "
        f"to {risk.incoming} dependent file(s).",
    ]
    if not documented:
        items.append(
            "- Knowledge risk: with no written rationale, the design only "
            "exists in the heads of past contributors."
        )
    items.append(
        "- Change risk: new contributors cannot distinguish deliberate "
        "behavior from accident, making refactors hazardous."
    )
    return "\n".join(items)


def _review_section(name) -> str:
    return "\n".join([
        "This ADR was **generated automatically by GapMap** and is a draft.",
        "",
        "A human should confirm:",
        "",
        "- [ ] Is the inferred decision actually why this module exists?",
        "- [ ] Are there constraints (performance, compliance, history) not visible in the code?",
        "- [ ] Which team owns this module going forward?",
        "- [ ] Should any of the listed dependents be decoupled?",
    ])


def _assemble(name, context, decision, role, tradeoffs, risks, review) -> str:
    return f"""# ADR: {name}

- **Status:** Draft (auto-generated by GapMap)
- **Date:** {date.today().isoformat()}

## Context

{context}

## Inferred Decision

{decision}

## Systemic Role

{role}

## Trade-offs

{tradeoffs}

## Risks

{risks}

## Recommended Human Review

{review}
"""
