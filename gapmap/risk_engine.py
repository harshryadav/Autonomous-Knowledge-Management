"""Phase 4 - Risk scoring.

MVP formula (deliberately simple and explainable):

    Risk Score = Incoming Dependencies x Lines of Code

A file that many other files import *and* that contains a lot of code
is load-bearing: changes to it have a wide blast radius. Zero incoming
dependencies -> zero risk score (nothing depends on it yet).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import networkx as nx


@dataclass
class FileRisk:
    path: str
    loc: int
    incoming: int    # number of files that import this one
    outgoing: int    # number of files this one imports
    score: int       # incoming * loc

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "loc": self.loc,
            "incoming": self.incoming,
            "outgoing": self.outgoing,
            "score": self.score,
        }


def compute_risks(graph: nx.DiGraph) -> List[FileRisk]:
    """Score every node, highest risk first (ties broken by path)."""
    risks = []
    for node, data in graph.nodes(data=True):
        loc = int(data.get("loc", 0))
        incoming = graph.in_degree(node)
        outgoing = graph.out_degree(node)
        risks.append(
            FileRisk(
                path=node,
                loc=loc,
                incoming=incoming,
                outgoing=outgoing,
                score=incoming * loc,
            )
        )
    risks.sort(key=lambda r: (-r.score, r.path))
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
