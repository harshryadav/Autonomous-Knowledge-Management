"""GapMap - find the riskiest undocumented code in a repository.

Pipeline: parse Python files -> extract entities (tree-sitter) ->
build an entity call graph -> score risk (in-degree x entity LOC) ->
check which risky entities are undocumented -> audit / explain /
generate ADRs / report.
"""

__version__ = "0.1.0"
