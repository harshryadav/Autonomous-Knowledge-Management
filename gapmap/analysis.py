"""One-stop repo analysis used by every CLI command.

Runs the full pipeline (parse -> entity graph -> entity risk -> doc
scan) once and hands back a single ``RepoAnalysis`` object.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import networkx as nx

from gapmap.doc_scanner import DocScan, scan_entity_docs
from gapmap.graph_builder import build_graph, dependencies_of, importers_of
from gapmap.parser import EntityInfo, ModuleInfo, entity_key, scan_repo
from gapmap.risk_engine import EntityRisk, compute_risks


@dataclass
class RepoAnalysis:
    root: Path
    modules: Dict[str, ModuleInfo]
    graph: nx.DiGraph
    entities: Dict[str, EntityInfo]     # unified registry
    risks: List[EntityRisk]             # sorted, highest risk first
    docs: DocScan

    # ------------------------------------------------------------------ #
    # Lookups
    # ------------------------------------------------------------------ #
    def risk_for(self, key: str) -> Optional[EntityRisk]:
        for risk in self.risks:
            if risk.key == key:
                return risk
        return None

    def rank_of(self, key: str) -> Optional[int]:
        """1-indexed position in the entity risk ranking."""
        for i, risk in enumerate(self.risks, start=1):
            if risk.key == key:
                return i
        return None

    def importers_of(self, key: str) -> List[str]:
        return importers_of(self.graph, key)

    def dependencies_of(self, key: str) -> List[str]:
        return dependencies_of(self.graph, key)

    def is_documented(self, key: str) -> bool:
        return self.docs.is_documented(key)

    # ------------------------------------------------------------------ #
    # Aggregates
    # ------------------------------------------------------------------ #
    def is_undocumented(self, key: str) -> bool:
        """Highly complex entity with no markdown or docstring mention."""
        entity = self.entities.get(key)
        if entity is None:
            return False
        return self.docs.is_undocumented(entity)

    def undocumented_risks(self) -> List[EntityRisk]:
        """Load-bearing, highly complex entities missing documentation."""
        return [
            r for r in self.risks
            if r.score > 0 and self.is_undocumented(r.key)
        ]

    def load_bearing(self) -> List[EntityRisk]:
        """Entities at least one other entity depends on."""
        return [r for r in self.risks if r.incoming > 0]

    def adr_coverage(self) -> float:
        """Share of load-bearing entities mentioned in docs (0..1)."""
        bearing = self.load_bearing()
        if not bearing:
            return 1.0
        documented = sum(1 for r in bearing if self.is_documented(r.key))
        return documented / len(bearing)

    def max_score(self) -> int:
        return self.risks[0].score if self.risks else 0

    # ------------------------------------------------------------------ #
    # Target resolution
    # ------------------------------------------------------------------ #
    def resolve_target(self, name: str) -> Optional[str]:
        """Resolve a user-provided name to an entity key.

        Accepts:
        - ``payment_router.py::route_payment`` (exact key)
        - ``route_payment`` (unique entity name)
        - ``payment_router.py`` / ``payment_router`` (riskiest entity in file)
        """
        name = name.strip().replace("\\", "/")

        if name in self.entities:
            return name
        if "::" in name and name in self.graph:
            return name

        # Exact entity name match.
        name_hits = [k for k, e in self.entities.items() if e.entity_name == name]
        if len(name_hits) == 1:
            return name_hits[0]
        if name_hits:
            return _pick_riskiest(name_hits, self.risks)

        # File path or basename -> riskiest entity in that file.
        if name in self.modules:
            return _pick_riskiest_in_file(name, self.risks)
        candidates = [
            p for p in self.modules
            if Path(p).name == name or Path(p).stem == name
        ]
        if len(candidates) == 1:
            return _pick_riskiest_in_file(candidates[0], self.risks)
        if candidates:
            keys = [
                r.key for r in self.risks if r.file in candidates
            ]
            return _pick_riskiest(keys, self.risks) if keys else None
        return None


def _pick_riskiest(keys: List[str], risks: List[EntityRisk]) -> Optional[str]:
    ranked = [r.key for r in risks if r.key in keys]
    return ranked[0] if ranked else keys[0]


def _pick_riskiest_in_file(file: str, risks: List[EntityRisk]) -> Optional[str]:
    in_file = [r.key for r in risks if r.file == file]
    return in_file[0] if in_file else None


def analyze(root: str | Path) -> RepoAnalysis:
    """Run the full GapMap pipeline against a repository."""
    root = Path(root).resolve()
    modules = scan_repo(root)
    entities: Dict[str, EntityInfo] = {}
    for info in modules.values():
        for entity in info.entities:
            entities[entity.key] = entity
    graph = build_graph(modules)
    risks = compute_risks(graph)
    docs = scan_entity_docs(root, entities.values())
    return RepoAnalysis(
        root=root,
        modules=modules,
        graph=graph,
        entities=entities,
        risks=risks,
        docs=docs,
    )
