# TrackFlow knowledge indexing

TrackFlow's commercial knowledge base prepares the four source documents and
indexes them into the dedicated `trackflow_knowledge` Qdrant collection. The
briefing is not indexed. Retrieval and grounded generation are implemented in
`pipeline.py`; end-to-end design and current evaluation are in `docs/rag/rag-design.md`.

## Semantic boundaries

`indexing.prepare_chunks()` parses Markdown blocks with markdown-it-py. Complete
paragraphs and lists form semantic units, preserving list introductions, procedure
steps, contract conditions and geographic coverage. Heading ancestry is retained
in `section`. No character-based truncation or overlap is applied. Indexing fails
if any required document is missing or produces fewer than three chunks.

Payload fields are `company`, `source_document`, `section`, `language`,
`chunk_index` and `text`, with the exact source identifiers from the briefing.

Current corpus preview: 14 chunks, with 3 for SLA delivery, 5 for returns,
3 for carrier coverage and 3 for storage pricing. Paragraph/list sizes range
from 138 to 532 characters. Source text preservation, deterministic identifiers,
repeat setup and stale-point removal were verified with in-memory Qdrant and
mocked embeddings. These checks do not validate real embedding quality.

## Configuration

Install the root project dependencies with `uv sync`. Configure these environment
variables outside version control using the actual student access from 4Geeks:

- `RAG_EMBEDDING_BASE_URL`: OpenAI-compatible embeddings API base URL.
- `RAG_EMBEDDING_API_KEY`: embeddings credential; never commit its value.
- `RAG_EMBEDDING_MODEL`: dedicated embeddings model ID.
- `RAG_GENERATION_MODEL`: distinct chat/completion model ID.
- `RAG_GENERATION_BASE_URL`: optional OpenAI-compatible generation endpoint; defaults to the embeddings URL.
- `RAG_GENERATION_API_KEY`: optional separate generation credential; defaults to the embeddings key.
- `QDRANT_URL`: Qdrant endpoint, default `http://localhost:6333`.
- `QDRANT_API_KEY`: optional credential for a secured Qdrant instance.

The provider's actual model IDs, API compatibility and connectivity remain to be
confirmed. No default model ID or embedding dimension is assumed. The collection
uses cosine distance, with dimension inferred from real embeddings. Qdrant handles
cosine normalization; the source text is embedded without rewriting its content.

From the repository root:

```bash
uv run python -m services.knowledge.indexing --preview
uv run python -m services.knowledge.indexing
```

The preview needs no external services or credentials. Actual setup requires a
running Qdrant instance and the configured embeddings service.

## Development idempotence

`setup()` embeds and validates the complete corpus before changing Qdrant. It
rejects an existing collection with incompatible vector size or distance. UUIDs
are deterministic over the complete payload. It upserts current points, then
deletes obsolete points from this dedicated collection after a successful upsert.
Re-running setup therefore removes chunks changed or deleted from the corpus
without duplicating unchanged points. Do not share this collection with another
indexer. Reindex after changing the embedding model, even if its dimension matches.

Publication is not atomic: concurrent readers can see old and new points during
an update. A failed upsert never triggers stale-point cleanup; rerun setup after
resolving the failure. Run only one indexer at a time in development.

## Retrieval, API, UI and evaluation

The retrieval/generation pipeline is in `pipeline.py`. It embeds the question,
retrieves up to five points, filters by cosine score (default 0.35), and asks a
distinct chat model to answer only from cited evidence. `POST /knowledge/query`
is authenticated; the backoffice page is `/knowledge`. The endpoint reuses this
RAG domain pipeline directly. `data/pipelines/pipeline.py` is the separate
Prefect/SQL business-KPI ETL, not a RAG pipeline; importing it here would couple
question-answering to an unrelated scheduled reporting flow.

Run the retrieval evaluation from the repository root after indexing:

```bash
uv run --env-file .env python -m scripts.evaluate_rag
```

On 2026-10-30 the real Qdrant index held 14 chunks with 1024-dimensional
embeddings. The original eight-query evaluation returned Recall@3 1.00 (8/8;
target 0.80). After expanding the set to eleven queries, live evaluation again
returned Recall@3 1.00 (11/11). One real generation check for
international returns cited the source section and preserved the
manual-handling caveat. These results do not replace continued review or
production monitoring; see `docs/rag/rag-design.md`.