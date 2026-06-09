"""One-stop repo analysis used by every CLI command.

Runs the full pipeline (parse -> graph -> risk -> doc scan) once and
hands back a single `RepoAnalysis` object so audit / ask / generate /
report all reason over the same consistent snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import networkx as nx

from gapmap.doc_scanner import DocScan, scan_docs
from gapmap.graph_builder import build_graph, dependencies_of, importers_of
from gapmap.parser import ModuleInfo, scan_repo
from gapmap.risk_engine import FileRisk, compute_risks


@dataclass
class RepoAnalysis:
    root: Path
    modules: Dict[str, ModuleInfo]
    graph: nx.DiGraph
    risks: List[FileRisk]            # sorted, highest risk first
    docs: DocScan

    # ------------------------------------------------------------------ #
    # Lookups
    # ------------------------------------------------------------------ #
    def risk_for(self, path: str) -> Optional[FileRisk]:
        for risk in self.risks:
            if risk.path == path:
                return risk
        return None

    def rank_of(self, path: str) -> Optional[int]:
        """1-indexed position in the risk ranking."""
        for i, risk in enumerate(self.risks, start=1):
            if risk.path == path:
                return i
        return None

    def importers_of(self, path: str) -> List[str]:
        return importers_of(self.graph, path)

    def dependencies_of(self, path: str) -> List[str]:
        return dependencies_of(self.graph, path)

    def is_documented(self, path: str) -> bool:
        return self.docs.is_documented(path)

    # ------------------------------------------------------------------ #
    # Aggregates
    # ------------------------------------------------------------------ #
    def undocumented_risks(self) -> List[FileRisk]:
        """Files with real risk (someone depends on them) and no docs."""
        return [
            r for r in self.risks
            if r.score > 0 and not self.is_documented(r.path)
        ]

    def load_bearing(self) -> List[FileRisk]:
        """Files at least one other file depends on."""
        return [r for r in self.risks if r.incoming > 0]

    def adr_coverage(self) -> float:
        """Share of load-bearing files that are mentioned in docs (0..1)."""
        bearing = self.load_bearing()
        if not bearing:
            return 1.0
        documented = sum(1 for r in bearing if self.is_documented(r.path))
        return documented / len(bearing)

    def max_score(self) -> int:
        return self.risks[0].score if self.risks else 0

    # ------------------------------------------------------------------ #
    # Target resolution ("payment_router.py" -> "src/payment_router.py")
    # ------------------------------------------------------------------ #
    def resolve_target(self, name: str) -> Optional[str]:
        name = name.strip().replace("\\", "/")
        if name in self.modules:
            return name
        candidates = [
            p for p in self.modules
            if Path(p).name == name or Path(p).stem == name
        ]
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            # Ambiguous basename: prefer the riskiest match.
            ranked = sorted(
                candidates,
                key=lambda p: -(self.risk_for(p).score if self.risk_for(p) else 0),
            )
            return ranked[0]
        return None


def analyze(root: str | Path) -> RepoAnalysis:
    """Run the full GapMap pipeline against a repository."""
    root = Path(root).resolve()
    modules = scan_repo(root)
    graph = build_graph(modules)
    risks = compute_risks(graph)
    docs = scan_docs(root, modules.keys())
    return RepoAnalysis(
        root=root, modules=modules, graph=graph, risks=risks, docs=docs
    )
