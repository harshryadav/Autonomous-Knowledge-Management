"""Phase 3 - Repository knowledge graph.

Node = file (relative path), edge = import relationship
(``checkout.py -> payment_router.py`` means checkout imports the
router). Built with NetworkX so downstream layers get in/out degrees,
traversal, and centrality for free.
"""

from __future__ import annotations

from typing import Dict, List

import networkx as nx

from gapmap.parser import ModuleInfo


def build_graph(modules: Dict[str, ModuleInfo]) -> nx.DiGraph:
    """Turn parsed modules into a directed import graph."""
    graph = nx.DiGraph()
    for rel, info in modules.items():
        graph.add_node(rel, loc=info.loc)
    for rel, info in modules.items():
        for dep in info.local_deps:
            if dep in modules:
                graph.add_edge(rel, dep)
    return graph


def importers_of(graph: nx.DiGraph, path: str) -> List[str]:
    """Files that depend on `path` (incoming edges)."""
    if path not in graph:
        return []
    return sorted(graph.predecessors(path))


def dependencies_of(graph: nx.DiGraph, path: str) -> List[str]:
    """Files that `path` depends on (outgoing edges)."""
    if path not in graph:
        return []
    return sorted(graph.successors(path))
