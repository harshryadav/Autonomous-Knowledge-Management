"""Phase 3 - Entity-level dependency graph.

Node = ``file_path::entity_name`` (a top-level class or function).
Edge = caller -> callee when the caller's body invokes or instantiates
another local entity (resolved from tree-sitter ``outgoing_calls``).

Built with NetworkX so downstream layers get in/out degrees for free.
"""

from __future__ import annotations

from typing import Dict, List

import networkx as nx

from gapmap.parser import EntityInfo, ModuleInfo, entity_key


def build_graph(modules: Dict[str, ModuleInfo]) -> nx.DiGraph:
    """Build a directed entity-level call graph across the repository."""
    name_index = _build_name_index(modules)
    graph = nx.DiGraph()

    for info in modules.values():
        for entity in info.entities:
            graph.add_node(
                entity.key,
                file=entity.file,
                entity_name=entity.entity_name,
                entity_type=entity.entity_type,
                loc=entity.loc,
                start_line=entity.start_line,
                end_line=entity.end_line,
            )

    for info in modules.values():
        for entity in info.entities:
            caller = entity.key
            for call in entity.outgoing_calls:
                for target in _resolve_call(call, entity.file, name_index):
                    if target != caller and target in graph:
                        graph.add_edge(caller, target)

    return graph


def importers_of(graph: nx.DiGraph, key: str) -> List[str]:
    """Entities that call or instantiate ``key`` (incoming edges)."""
    if key not in graph:
        return []
    return sorted(graph.predecessors(key))


def dependencies_of(graph: nx.DiGraph, key: str) -> List[str]:
    """Entities that ``key`` calls or instantiates (outgoing edges)."""
    if key not in graph:
        return []
    return sorted(graph.successors(key))


def _build_name_index(modules: Dict[str, ModuleInfo]) -> Dict[str, List[str]]:
    """Map bare entity names to fully-qualified ``file::name`` keys."""
    index: Dict[str, List[str]] = {}
    for info in modules.values():
        for entity in info.entities:
            index.setdefault(entity.entity_name, []).append(entity.key)
    for keys in index.values():
        keys.sort()
    return index


def _resolve_call(
    call_name: str, source_file: str, name_index: Dict[str, List[str]]
) -> List[str]:
    """Resolve a callee name to entity key(s), preferring same-file matches."""
    candidates = name_index.get(call_name, [])
    if not candidates:
        return []
    same_file = [k for k in candidates if k.startswith(f"{source_file}::")]
    return same_file if same_file else candidates
