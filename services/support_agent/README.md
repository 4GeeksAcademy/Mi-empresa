# TrackFlow support agent - graph foundation

The existing RAG is wrapped in a compiled LangGraph state machine and exposed as
an authenticated FastAPI endpoint. Checkpoints and execution traces are persisted
in SQLite but are separate records with separate purposes.

## Reuse and state

The RAG implementation lives in `services/knowledge`, rather than the assignment's
suggested `data/pipelines` location. The graph imports its `retrieve` and
`generate_answer` functions directly, with no copying or second retrieval.
`setup`, `embed` and the original `query` remain unchanged. Access to
`data/pipelines` is restricted by the organization's content policy.

The input contains only `question`. State adds retrieved `context`, final
`answer`, and a nullable validation `error`; it retains no conversation history.
The receive node validates the runtime input type and trims whitespace.
TypedDict annotations describe node contracts; LangGraph compilation does not
perform Python static type checking.

```text
START -> receive -- empty question --> invalid_question -> END
                  |
                  +-- valid --> retrieve -- no context --> no_context -> END
                                        |
                                        +-- context --> generate -> END
```

Retrieval preserves the existing defaults: at most five valid TrackFlow payloads
with cosine similarity >= 0.35. With no evidence, a fixed honest answer avoids
calling the model. Generation uses only the already retrieved context, retaining
the existing prompt, citations, policies and provider configuration.

## Dependencies

From the repository root:

```bash
uv sync
uv sync --project services/api --extra test
```

LangGraph and its SQLite checkpointer are declared in both Python projects.
The API's `requirements.txt` uses the same `qdrant-client>=1.15,<1.17` range as
the uv project manifests, compatible with the local Qdrant 1.15.4 server.

## Lifecycle and checkpoints

```python
from pathlib import Path
from uuid import uuid4

from services.support_agent.graph import open_agent_graph

config = {"configurable": {"thread_id": str(uuid4())}}

with open_agent_graph(Path(".agent-data/checkpoints.sqlite3")) as graph:
    result = graph.invoke(
        {"question": "¿Las devoluciones internacionales son automáticas?"},
        config,
        durability="sync",
    )
    snapshot = graph.get_state(config)
    checkpoints = list(graph.get_state_history(config))
```

Opening the context creates the SQLite schema, compiles the graph and validates
reachability from START and a path to END for every node. Structural errors stop
startup before the compiled graph is exposed. Keep this context open for the
application's lifetime; do not open and compile it per request.

The API generates a fresh UUID per request and uses it as both the checkpoint
thread ID and trace ID. Trace lookup is authenticated and owner-scoped; another
user receives 404. The public API does not expose checkpoint resume.

`durability="sync"` writes each checkpoint before the next step starts.
After a failed generation, reopen the same database, restore the same config and
call `graph.invoke(None, config, durability="sync")`. This resumes the pending
node without calling retrieval again. Completed runs have `snapshot.next == ()`.
Do not pass the original question again when resuming: that starts another input
on the thread rather than resuming the failed step.

SqliteSaver serializes its shared connection access; the connection has a
30-second busy timeout and is closed when the context exits, including on a
compilation failure. Trace writes are serialized within each API process.
SQLite is appropriate for this local, small-scale phase,
not a claim of production readiness for multiple API workers. The database
directory must be on persistent storage to survive container replacement.

Checkpoint and trace records contain questions and retrieved documents. Keep the
directory private, do not commit it, and do not expose it through static-file
serving. No external tracing provider is configured.

## FastAPI endpoint and traces

The API compiles the graph during its lifespan and keeps the SQLite connection
open until shutdown. Set `TRACKFLOW_AGENT_DATA_DIR` to a persistent, private
directory; by default it uses the repository's ignored `.agent-data/` directory.
The SQLite file is `agent.sqlite3`, shared by LangGraph checkpoints and the
separate `agent_traces` table. Container deployments must mount persistent
storage at that path if data must survive container replacement. This local
single-file design is not intended for multiple API replicas.

- `POST /agent/query` requires the existing Bearer authentication. Request:
  `{"question":"¿Las devoluciones internacionales son automáticas?"}`.
  Success returns `{"answer":"...","trace_id":"<uuid>"}`.
- `GET /agent/traces/{trace_id}` returns the trace only to its owner; unknown,
  malformed and foreign IDs all return 404.
- Empty/whitespace questions return HTTP 422 and still have a queryable rejected
  trace. A node failure returns HTTP 503 with a sanitized message and trace ID.

A trace stores the input question, ordered node outputs, routing decisions,
retrieved source payloads, answer, status and sanitized error code. It does not
store model reasoning or raw exception messages. Internal logs include the trace
ID and exception type only. Checkpoint history supports node recovery; the trace
is the durable, queryable execution record. Each node update is saved before the
next node begins, so a failed run retains the completed steps.

## Offline trace evaluations

Run the four saved-trace evaluations from the repository root:

```bash
uv run python -m pytest tests/pipelines/test_agent_evals.py -q
```

For acceptance evaluation, export three authenticated trace JSON objects (a
grounded returns query, an empty question, and a query with no retrieved context)
from `GET /agent/traces/{trace_id}` and run:

```bash
uv run python -m scripts.evaluate_agent_traces \
  --require-all \
  /path/to/grounded-returns.json \
  /path/to/empty-question.json \
  /path/to/no-context.json
```

For a single authentic end-to-end grounding run from the repository root, with
provider credentials already configured in `.env`, capture and evaluate it
without printing credentials:

```bash
uv run --project services/api --env-file .env \
  python -m scripts.capture_agent_trace \
  --question "¿Las devoluciones internacionales son automáticas y quién las gestiona?" \
  --output .agent-data/agent-trace-returns.json

uv run --project services/api --env-file .env \
  python -m scripts.evaluate_agent_traces \
  .agent-data/agent-trace-returns.json
```

The capture calls the configured embedding service and approved generation
endpoint with the question and retrieved context. Do not use it unless that
provider is approved to process those documents. The `.agent-data/` export is
git-ignored by default; review and sanitize it before sharing.

The CLI validates node order and context handoff, the empty-question route,
the no-context route, and grounding of the international-returns fact in the
`returns-policy` source. It reads JSON exports only; it never invokes LangGraph,
Qdrant, embeddings or generation. It refuses fixtures marked
`synthetic_test_fixture` as acceptance evidence and returns nonzero for missing
or failed cases.

`tests/pipelines/fixtures/agent-trace-returns.json` is a sanitized export from an
authorized live provider run. It records the actual retrieval, generation input,
answer and source, and passes both `flow` and `briefing_grounding`. The other
fixtures are explicitly marked `synthetic_test_fixture`; they test empty-input
and no-context evaluation logic but are not evidence of live provider behavior.

## Focused verification

```bash
uv run --project services/api --extra test \
  python -m pytest tests/pipelines/test_agent_graph.py tests/pipelines/test_rag.py -q
```

These unit tests mock retrieval/generation: they verify node order, conditional
routes, compilation failures, thread separation and checkpoint recovery after
closing/reopening SQLite. They do not prove live provider availability, retrieval
quality, or answer grounding. The offline eval unit-test command above includes
the sanitized authorized grounding trace and was validated locally: 7 passed.
