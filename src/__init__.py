"""Autonomous Knowledge Management - core package.

This is the retrieval / intelligence layer: ingestion -> chunking ->
embeddings -> vector retrieval. Each submodule is deliberately
decoupled so later work (entity extraction, knowledge graphs, Q&A)
can slot in on top without reshaping the rest of the pipeline.
"""

from src.schema import Document, Chunk
from src.pipeline import Pipeline

__all__ = ["Document", "Chunk", "Pipeline"]
