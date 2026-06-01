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
| Q&A / answer synthesis (grounded, cited) | Done | `src/qa.py` |
| Orchestration + CLI | Done | `src/pipeline.py`, `main.py` |
| Unit tests (deterministic fake encoder + LLM) | Done | `tests/` |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Index the sample repo and run the default demo queries.
python main.py --repo data/repo1 -v

# Retrieve raw chunks for a query.
python main.py --repo data/repo1 --query "Where is caching used?"

# Ask a question and get a synthesized, cited answer.
python main.py --repo data/repo1 --ask "Where is caching used and why?"

# Drop into an interactive prompt.
python main.py --repo data/repo1 --interactive

# Persist the index so repeat runs skip re-embedding.
python main.py --repo data/repo1 --save .cache/repo1
```

### Answer synthesis (Q&A)

`--ask` runs the full **retrieve → synthesize** path: it embeds the
question, pulls the most relevant chunks, packs them into a
token-bounded, citation-tagged context block, and asks a language model
to answer **using only that context**. Every answer carries its
`Citation`s, a `confidence` score (mean similarity of the sources used),
and the `strategy` that produced it.

The LLM client is injectable and **optional**. With no `openai` install
and no API key, the system transparently falls back to a deterministic
`ExtractiveLLM` that quotes the retrieved sources — so the Q&A path
works offline, in CI, and in demos with zero setup. To enable the
LLM-backed path:

```bash
pip install "openai>=1.30,<2.0"
export OPENAI_API_KEY=sk-...
python main.py --repo data/repo1 --ask "Why was caching added?"
```

If the model call fails at runtime (timeout, rate limit, bad response),
the synthesizer degrades to the extractive answer rather than erroring.

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
    -> src/qa.py               (RetrievalResults -> grounded Answer)
    -> src/pipeline.py         (glue + query/answer API)
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
