"""CLI entrypoint for the retrieval pipeline.

Usage:
    python main.py --repo data/repo1 --query "What does this repo do?"
    python main.py --repo data/repo1 --interactive

Building the index and querying are intentionally separated at the
API level (see `src/pipeline.py`); this CLI just does both in one
shot for convenience. Use `--save` to persist the index so repeat
runs skip re-embedding.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List

from src.config import PipelineConfig
from src.pipeline import Pipeline
from src.retrieval import RetrievalResult


DEFAULT_QUERIES = [
    "What does this repo do?",
    "Where is caching used?",
    "What functions are defined?",
]


def build_pipeline(repo_path: str, top_k: int) -> Pipeline:
    config = PipelineConfig.default()
    config.top_k = top_k
    pipeline = Pipeline(config=config)
    pipeline.build(repo_path)
    return pipeline


def print_results(query: str, results: List[RetrievalResult]) -> None:
    print(f"\n=== Query: {query}")
    if not results:
        print("(no results)")
        return
    for r in results:
        location = r.chunk.file
        if r.chunk.function:
            location += f"::{r.chunk.function}"
        if r.chunk.start_line is not None:
            location += f":L{r.chunk.start_line}"
        print(f"\n[{r.rank}] score={r.score:.3f} [{r.chunk.type}] {location}")
        preview = r.chunk.content.strip().replace("\n", " ")
        if len(preview) > 240:
            preview = preview[:240] + "..."
        print(f"    {preview}")


def run_interactive(pipeline: Pipeline) -> None:
    print("Type a query and press Enter. Blank line, Ctrl-D, or Ctrl-C to quit.")
    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            # Clean exit on Ctrl-D / Ctrl-C - no scary traceback.
            print()
            return
        if not query:
            return
        try:
            results = pipeline.query(query)
        except KeyboardInterrupt:
            print("\n(interrupted)")
            return
        print_results(query, results)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous Knowledge Management retriever"
    )
    parser.add_argument("--repo", required=True, help="Path to the repo to index")
    parser.add_argument("--query", action="append", default=[], help="Query (may be repeated)")
    parser.add_argument("--top-k", type=int, default=5, help="Results per query")
    parser.add_argument("--interactive", action="store_true", help="Prompt loop after indexing")
    parser.add_argument("--save", help="Optional directory to persist the built index")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pipeline = build_pipeline(args.repo, args.top_k)

    queries = args.query or (DEFAULT_QUERIES if not args.interactive else [])
    for q in queries:
        print_results(q, pipeline.query(q))

    if args.interactive:
        run_interactive(pipeline)

    if args.save:
        pipeline.save(args.save)
        print(f"\nSaved index to {args.save}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # Exit code 130 is the POSIX convention for "killed by SIGINT".
        print()
        sys.exit(130)
