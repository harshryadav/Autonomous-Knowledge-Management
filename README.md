# Autonomous Knowledge Management

Intelligent knowledge-management system that extracts architectural and
implementation knowledge from source code, builds queryable structures
over it, and helps developers understand the "why" behind decisions.

The work is planned in four weekly milestones (see `PROJECT_PLAN.md`).
The current branch implements the first milestone: an end-to-end
retrieval baseline that ingests a repository, chunks its text, embeds
every chunk, and answers free-form queries by returning the most
relevant chunks.

## What's in this branch

| Layer | Status | Module |
|-------|--------|--------|
| Ingestion (README + code + comments + docstrings) | Done | `src/ingestion.py` |
| Chunking (prose + code, with overlap) | Done | `src/chunking.py` |
| Embeddings (Sentence-BERT, L2-normalized) | Done | `src/embeddings.py` |
| Vector search (FAISS, cosine similarity) | Done | `src/retrieval.py` |
| Orchestration + CLI | Done | `src/pipeline.py`, `main.py` |
| Unit tests (deterministic fake encoder) | Done | `tests/` |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Index the sample repo and run the default demo queries.
python main.py --repo data/repo1 -v

# Ask a specific question.
python main.py --repo data/repo1 --query "Where is caching used?"

# Drop into an interactive prompt.
python main.py --repo data/repo1 --interactive

# Persist the index so repeat runs skip re-embedding.
python main.py --repo data/repo1 --save .cache/repo1
```

## Running the tests

The test suite uses a deterministic fake encoder, so it runs fast and
does not require network access or model downloads.

```bash
pytest
```

## Architecture

```
repo on disk
    -> src/ingestion.py        (files -> Documents)
    -> src/chunking.py         (Documents -> Chunks)
    -> src/embeddings.py       (Chunks -> normalized vectors)
    -> src/retrieval.py        (vectors + Chunks -> FAISS index)
    -> src/pipeline.py         (glue + query API)
```

All cross-layer contracts are defined in `src/schema.py` so later
work (entity extraction, knowledge graph construction, Q&A) can be
added without disturbing retrieval.

## Shared data schema

Every piece of knowledge - a README paragraph, a function's docstring,
a single `#` comment - eventually becomes a `Chunk`:

```json
{
  "type": "comment",
  "content": "look up the key in the cache",
  "file": "cache.py",
  "function": "get",
  "start_line": 12,
  "end_line": 12,
  "chunk_index": 0,
  "extra": {}
}
```

This mirrors the integration format specified in `PROJECT_PLAN.md`.
