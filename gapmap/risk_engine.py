"""Phase 4 - Entity-level risk scoring.

MVP formula (deliberately simple and explainable):

    Risk Score = In-Degree x Entity LOC

In-degree counts how many *other entities* call or instantiate this one.
Entity LOC is the non-blank lines inside that class or function only.
Zero in-degree -> zero risk (nothing in the codebase depends on it yet).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import networkx as nx


@dataclass
class EntityRisk:
    """Risk profile for a single class or function."""

    key: str              # file::entity_name
    file: str
    entity_name: str
    entity_type: str      # "class" or "function"
    loc: int              # lines of code for this entity only
    incoming: int         # entities that call / instantiate this one
    outgoing: int         # entities this one calls / instantiates
    score: int            # incoming * loc

    @property
    def path(self) -> str:
        """Backward-compatible alias used by older CLI/report code."""
        return self.key

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "file": self.file,
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "loc": self.loc,
            "incoming": self.incoming,
            "outgoing": self.outgoing,
            "score": self.score,
        }


# Backward-compatible alias
FileRisk = EntityRisk


def compute_risks(graph: nx.DiGraph) -> List[EntityRisk]:
    """Score every entity node, highest risk first (ties broken by key)."""
    risks: List[EntityRisk] = []
    for node, data in graph.nodes(data=True):
        loc = int(data.get("loc", 0))
        incoming = graph.in_degree(node)
        outgoing = graph.out_degree(node)
        risks.append(
            EntityRisk(
                key=node,
                file=str(data.get("file", node.split("::", 1)[0])),
                entity_name=str(data.get("entity_name", node.split("::", 1)[-1])),
                entity_type=str(data.get("entity_type", "function")),
                loc=loc,
                incoming=incoming,
                outgoing=outgoing,
                score=incoming * loc,
            )
        )
    risks.sort(key=lambda r: (-r.score, r.key))
    return risks


def risk_level(score: int, max_score: int) -> str:
    """Relative bucket used for red/yellow/green labels in the UI."""
    if max_score <= 0 or score <= 0:
        return "low"
    ratio = score / max_score
    if ratio >= 0.5:
        return "high"
    if ratio >= 0.15:
        return "medium"
    return "low"
