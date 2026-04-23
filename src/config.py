"""Central configuration for the retrieval pipeline.

Kept as a plain dataclass rather than a YAML/TOML file so it's easy
to import, override in tests, and extend later. When this outgrows
a single dataclass, we can swap in pydantic-settings or similar
without touching call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Sentence-BERT model pinned to the small, fast default. Good enough
# as a starting point; revisit once we have retrieval-quality metrics
# to compare against.
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIM = 384  # matches all-MiniLM-L6-v2


@dataclass
class PipelineConfig:
    """Tunables for ingestion + chunking + embedding + retrieval."""

    model_name: str = DEFAULT_MODEL_NAME
    embedding_dim: int = DEFAULT_EMBEDDING_DIM

    # Chunking
    prose_chunk_size: int = 150          # words per chunk for README / docs
    prose_chunk_overlap: int = 30        # word overlap to keep boundary context
    code_chunk_size: int = 40            # lines per chunk for source files
    code_chunk_overlap: int = 8

    # Ingestion
    code_extensions: tuple = (".py",)    # Python-only for now; extend as needed
    readme_names: tuple = ("README.md", "README.rst", "README.txt", "README")
    max_file_bytes: int = 1_000_000      # skip giant generated files

    # Retrieval
    top_k: int = 5

    # Encoding
    batch_size: int = 32

    @classmethod
    def default(cls) -> "PipelineConfig":
        return cls()


def project_root() -> Path:
    """Best-effort repo root for default data paths."""
    return Path(__file__).resolve().parent.parent
