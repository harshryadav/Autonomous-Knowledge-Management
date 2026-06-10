"""Phase 8 - ADR generator.

``gapmap generate route_payment`` drafts an entity-focused ADR using
the entity's source block (not the whole file), graph centrality, and
an optional LLM pass with a Principal Engineer system prompt.

Output path: ``docs/adr/00X_<entity_name>_ADR.md``
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import List, Optional

from gapmap.analysis import RepoAnalysis
from gapmap.llm import maybe_complete
from gapmap.parser import EntityInfo
from gapmap.risk_engine import risk_level

ADR_DIR = "docs/adr"
ADR_SEQUENCE_RE = re.compile(r"^(\d{3})_.*_ADR\.md$")


def extract_entity_source(
    analysis: RepoAnalysis, entity: EntityInfo
) -> str:
    """Return only the source lines for this entity (not the whole file)."""
    path = analysis.root / entity.file
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    start = max(entity.start_line - 1, 0)
    end = min(entity.end_line, len(lines))
    return "\n".join(lines[start:end])


def adr_path_for(analysis: RepoAnalysis, key: str) -> Path:
    """Next numbered ADR path: ``docs/adr/00X_<entity_name>_ADR.md``."""
    entity = analysis.entities.get(key)
    name = entity.entity_name if entity else key.split("::")[-1]
    sequence = _next_adr_sequence(analysis.root)
    return analysis.root / ADR_DIR / f"{sequence:03d}_{name}_ADR.md"


def generate_adr(
    analysis: RepoAnalysis,
    entity_key: str,
    source_block: Optional[str] = None,
) -> str:
    """Generate an ADR for a specific entity node and its source block.

    ``entity_key`` format: ``payment_service.py::PaymentRouter``
    ``source_block`` defaults to the entity's lines from its parent file.
    """
    risk = analysis.risk_for(entity_key)
    if risk is None:
        raise ValueError(f"{entity_key} not found in the scanned repository")

    entity = analysis.entities.get(entity_key)
    if entity is None:
        raise ValueError(f"No entity metadata for {entity_key}")

    if source_block is None:
        source_block = extract_entity_source(analysis, entity)

    in_degree = risk.incoming
    importers = analysis.importers_of(entity_key)
    dependencies = analysis.dependencies_of(entity_key)
    documented = analysis.is_documented(entity_key)
    rank = analysis.rank_of(entity_key)
    level = risk_level(risk.score, analysis.max_score())
    label = f"{risk.entity_name} ({risk.entity_type} in {risk.file})"
    kind = "Class" if risk.entity_type == "class" else "Function"

    system = _principal_engineer_system(in_degree, kind)
    user = _llm_user_prompt(
        entity_key=entity_key,
        label=label,
        in_degree=in_degree,
        rank=rank,
        level=level,
        documented=documented,
        importers=importers,
        dependencies=dependencies,
        source_block=source_block,
    )

    llm_adr = maybe_complete(system=system, user=user, max_tokens=1200)
    if llm_adr:
        return _ensure_adr_header(llm_adr, risk.entity_name, entity_key)

    return _template_adr(
        analysis, entity_key, entity, risk, source_block,
        rank, level, documented, importers, dependencies, label,
    )


def build_adr(analysis: RepoAnalysis, key: str) -> str:
    """Backward-compatible alias for :func:`generate_adr`."""
    return generate_adr(analysis, key)


def write_adr(analysis: RepoAnalysis, key: str) -> Path:
    """Generate and save the ADR. Returns the output path."""
    output = adr_path_for(analysis, key)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generate_adr(analysis, key), encoding="utf-8")
    return output


# --------------------------------------------------------------------------- #
# LLM prompts
# --------------------------------------------------------------------------- #
def _principal_engineer_system(in_degree: int, kind: str) -> str:
    return (
        f"You are a Principal Engineer. Review this undocumented {kind}. "
        f"It has an in-degree centrality of {in_degree}, meaning it is a "
        f"critical, load-bearing component utilized heavily by the rest of "
        f"the system. Write an Architecture Decision Record (ADR) focusing "
        f"entirely on why this specific component is structured this way, "
        f"its exact architectural responsibilities, and the systemic risks "
        f"of modifying it."
    )


def _llm_user_prompt(
    *,
    entity_key: str,
    label: str,
    in_degree: int,
    rank: Optional[int],
    level: str,
    documented: bool,
    importers: List[str],
    dependencies: List[str],
    source_block: str,
) -> str:
    return f"""Entity: `{entity_key}` ({label})
Risk rank: #{rank} ({level})
In-degree (callers): {in_degree}
Documented: {"yes" if documented else "no"}
Called by: {", ".join(importers) or "none"}
Calls: {", ".join(dependencies) or "none"}

Source code (this entity only — not the full file):
```python
{source_block}
```

Write a complete ADR in markdown with these sections:
## Context
## Inferred Decision
## Architectural Responsibilities
## Systemic Role
## Trade-offs
## Risks
## Recommended Human Review

Ground every claim in the source code and call-graph facts above."""


# --------------------------------------------------------------------------- #
# Template fallback (offline / no API key)
# --------------------------------------------------------------------------- #
def _template_adr(
    analysis, entity_key, entity, risk, source_block,
    rank, level, documented, importers, dependencies, label,
) -> str:
    context = _context_section(label, risk, rank, level, documented, entity)
    decision = _decision_section(risk, importers, dependencies)
    responsibilities = _responsibilities_section(risk, source_block)
    role = _role_section(importers, dependencies)
    tradeoffs = _tradeoffs_section(risk)
    risks = _risks_section(risk, documented)
    review = _review_section(risk.entity_name)
    source_section = f"## Source Code\n\n```python\n{source_block}\n```"

    return _assemble(
        risk.entity_name, entity_key, label, context, decision,
        responsibilities, role, tradeoffs, risks, review, source_section,
    )


def _context_section(label, risk, rank, level, documented, entity) -> str:
    lines = [
        f"`{label}` is ranked **#{rank}** by risk in this repository "
        f"(risk score **{risk.score}** = in-degree {risk.incoming} "
        f"x {risk.loc} lines of code, {level} risk).",
    ]
    if entity is not None:
        lines.append(
            f"Source location: `{risk.file}` lines "
            f"{entity.start_line}-{entity.end_line}."
        )
    if documented:
        lines.append("Some documentation already mentions this entity.")
    else:
        lines.append(
            "No existing documentation mentions this entity by name, so "
            "this record was generated to close that gap."
        )
    return "\n\n".join(lines)


def _decision_section(risk, importers, dependencies) -> str:
    return (
        f"In-degree centrality of **{risk.incoming}** indicates "
        f"`{risk.entity_name}` is a load-bearing {risk.entity_type}: "
        f"{len(importers)} entity/entities call it directly. This is an "
        f"*inferred* decision reconstructed from the call graph and "
        f"source structure — confirm with the original authors."
    )


def _responsibilities_section(risk, source_block: str) -> str:
    preview = source_block.strip().splitlines()[0] if source_block.strip() else ""
    return (
        f"`{risk.entity_name}` owns the behaviour shown in its "
        f"{risk.loc}-line implementation. Review the source block below "
        f"to determine its exact contract with callers"
        + (f" (starts with: `{preview[:80]}`)." if preview else ".")
    )


def _role_section(importers, dependencies) -> str:
    lines = []
    if importers:
        lines.append("**Called by:**")
        lines.extend(f"- `{imp}`" for imp in importers)
    else:
        lines.append("No other entities currently call this one.")
    if dependencies:
        lines.append("")
        lines.append("**Calls / instantiates:**")
        lines.extend(f"- `{dep}`" for dep in dependencies)
    return "\n".join(lines)


def _tradeoffs_section(risk) -> str:
    return "\n".join([
        f"- **Centralization vs. blast radius.** {risk.incoming} caller(s) "
        f"depend on `{risk.entity_name}`; breaking changes propagate widely.",
        f"- **Size vs. reviewability.** {risk.loc} lines in this "
        f"{risk.entity_type} — changes need careful review.",
        "- **Implicit contract.** Behaviour is defined only by implementation.",
    ])


def _risks_section(risk, documented) -> str:
    items = [
        f"- **Modification risk:** in-degree {risk.incoming} — a regression "
        f"in `{risk.entity_name}` affects {risk.incoming} dependent "
        f"entity/entities.",
    ]
    if not documented:
        items.append(
            "- **Knowledge risk:** no written rationale exists for this "
            "component."
        )
    items.append(
        "- **Refactor risk:** contributors cannot distinguish deliberate "
        "design from accident."
    )
    return "\n".join(items)


def _review_section(name) -> str:
    return "\n".join([
        "This ADR was **generated automatically by GapMap** and is a draft.",
        "",
        "A human should confirm:",
        "",
        f"- [ ] Is the inferred structure of `{name}` intentional?",
        "- [ ] Are performance, compliance, or historical constraints missing?",
        "- [ ] Which team owns this component?",
        "- [ ] Should callers be decoupled to reduce blast radius?",
    ])


def _assemble(
    name, entity_key, label, context, decision,
    responsibilities, role, tradeoffs, risks, review, source_section,
) -> str:
    return f"""# ADR: {name}

- **Status:** Draft (auto-generated by GapMap)
- **Date:** {date.today().isoformat()}
- **Entity:** `{entity_key}`

## Context

{context}

## Inferred Decision

{decision}

## Architectural Responsibilities

{responsibilities}

## Systemic Role

{role}

## Trade-offs

{tradeoffs}

## Risks

{risks}

## Recommended Human Review

{review}

{source_section}
"""


def _ensure_adr_header(text: str, name: str, entity_key: str) -> str:
    """Prepend metadata if the LLM omitted the standard header."""
    if text.lstrip().startswith("# ADR"):
        return text
    header = (
        f"# ADR: {name}\n\n"
        f"- **Status:** Draft (auto-generated by GapMap)\n"
        f"- **Date:** {date.today().isoformat()}\n"
        f"- **Entity:** `{entity_key}`\n\n"
    )
    return header + text


def _next_adr_sequence(root: Path) -> int:
    """Next 001-style sequence number under ``docs/adr/``."""
    adr_dir = root / ADR_DIR
    if not adr_dir.is_dir():
        return 1
    highest = 0
    for path in adr_dir.iterdir():
        match = ADR_SEQUENCE_RE.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1
