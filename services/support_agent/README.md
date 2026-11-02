# TrackFlow support agent - RAG and MCP incidents

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
`answer`, a nullable validation `error`, the selected source and typed incident
query/result; it retains no conversation history.
The receive node validates the runtime input type and trims whitespace.
TypedDict annotations describe node contracts; LangGraph compilation does not
perform Python static type checking.

```text
START -> receive -- empty question --> invalid_question -> END
                  |
                  +-- policy --> retrieve -- no context --> no_context -> END
                  |                      +-- context --> generate -> END
                  +-- operational --> incidents -- success --> incident_answer -> END
                                              +-- failure --> tool_fallback
```

For mixed questions, `incidents` runs before `retrieve`; a tool failure first
visits `tool_fallback`. The documentation answer is appended to the real
operational answer (or its honest fallback). RAG never replaces missing live data.

## External incident tool (MCP)

`incidents.py` imports `IncidentFilters` and `IncidentResponse` from the existing
backend. `IncidentQuery` adds one positive `ticket_id`; otherwise it accepts the
real `status`, `origin`, `branch` and `category` filters. Contradictory filters or
multiple IDs require clarification rather than silently selecting a ticket.
`IncidentSuccess` and `IncidentFailure` distinguish real records from sanitized
error codes.

The agent loads `list_incidents` and `get_incident` with
`langchain-mcp-adapters` over authenticated Streamable HTTP. Only the MCP server
calls GET `/api/incidents` and GET `/api/incidents/{id}`. There is no
write operation, second dataset, indexing of tickets or operational-record
submission to the generation model. Responses render the API fields directly.
Empty search results are explicitly reported, not converted into invented tickets.

- `TRACKFLOW_MCP_URL`: required MCP URL ending in `/mcp`; HTTPS except loopback.
- `TRACKFLOW_MCP_TOKEN`: required OAuth access token for the agent, with only
  `mcp:access incidents:read`. Obtain and rotate it securely through the provider;
  it is never stored in graph state or traces. No automatic refresh is implemented.
- Old `TRACKFLOW_INCIDENTS_BASE_URL` and `TRACKFLOW_INCIDENTS_TOKEN` are no longer
  consumed. There is no HTTP fallback or second active path to Incidents Manager.
- The MCP server owns backend connectivity. Existing backend GET routes remain
  unauthenticated, so keep the backend private. Agent endpoints keep their
  original authenticated, owner-scoped behavior.
- Each call has a **5.0-second total deadline**, including reading the response,
  covering initialization, discovery, tool execution and session cleanup.
- Timeout, network failure, 404, 401/403, server failure and malformed payloads
  enter an explicit fallback node. Logs/traces store only sanitized error codes,
  not raw provider errors or credentials. The graph still completes honestly.

`routing.py` selects sources locally from the question: ticket references and
operational listing/status phrases use incidents, stable knowledge uses RAG,
and combined policy/operational questions use both. It supports common Spanish
and English phrases; it is a deterministic first-stage router, not an unrestricted
semantic classifier. Singular tickets without an ID and contradictory searches
ask for clarification. No user source-selection command is required.

Inventory remains outside the agent's deterministic router; the MCP server
exposes it to other authorized clients. Agent routing is unchanged.

See [MCP configuration, scopes, CLI and Playground](../../mcps/trackflow/README.md).
The MCP and agent are independent processes; running the backend alone is not
sufficient. Install the updated API dependencies before restarting it. The API's
existing uv lock has not been regenerated in this change; synchronize it in an
authorized environment before using a locked API install. The root uv lock is
updated and was used for focused graph/MCP validation.

Start and verify the existing backend from the repository root:

```bash
docker compose up -d backend
curl --max-time 5 http://localhost:8000/health
curl --max-time 5 http://localhost:8000/api/incidents
```

The full app also requires `DATABASE_URL` for inventory initialization. In this
environment, Compose mounts telemetry at `/docs/telemetry` while the code expects
`/app/docs/telemetry`; the checked local run uses an additional read-only mount.
With explicit developer approval, a local SQLite database can satisfy inventory
startup without changing the incident repository or creating tickets:

```bash
docker compose stop backend
docker compose run -d --no-deps --service-ports \
  --name mi-empresa-agent-local-backend \
  -v "$PWD/docs/telemetry:/app/docs/telemetry:ro" \
  -e DATABASE_URL=sqlite:////var/lib/trackflow/tasks/agent-local.db \
  -e TRACKFLOW_AGENT_DATA_DIR=/var/lib/trackflow/tasks/agent-data backend
curl --max-time 5 http://localhost:8000/health
```

This is an explicit local-development alternative, not a Supabase replacement.
Do not run it alongside another service using port 8000. To stop it, use
`docker stop mi-empresa-agent-local-backend`. Do not modify protected Compose or
environment files without approval.

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

Part 2 adds `routing_tool` (one existing ticket, no RAG), `routing_rag`
(documented policy, no tool), `routing_both` and `tool_fallback`. Evaluations inspect
ordered actual node events, source selection and returned operational fields,
not just response keywords. An empty live list has its own `routing_list` case;
it **does not satisfy** the existing-ticket acceptance case.

Capture real incident traces without invoking a model, then evaluate them together
with the existing authentic policy trace:

```bash
uv run --project services/api python -m scripts.capture_incident_evals
uv run --project services/api python -m scripts.evaluate_agent_traces \
  --require-external \
  .agent-data/incident-evals.json \
  tests/pipelines/fixtures/agent-trace-returns.json
```

The capture discovers a ticket from the real list and probes a missing ID above
the observed maximum, without creating or changing data. If the backend is empty,
it captures list/404 diagnostics and exits nonzero; `--require-external` also
fails because the existing-ticket case is absent. A concurrent insertion can make
the candidate ID exist; the fallback evaluation will then be missing, not fabricated.

The authentic policy fixture is prior Part 1 evidence. It verifies RAG-only
routing but does not claim a new live RAG provider run. To capture a fresh policy
trace, use the existing capture command below only with a provider approved to
process those documents.

Run the focused Part 2 tests:

```bash
uv run --project services/api --extra test python -m pytest \
  tests/pipelines/test_agent_external_tools.py \
  tests/pipelines/test_agent_graph.py tests/pipelines/test_agent_evals.py \
  services/api/tests/test_agent.py -q
```

HTTP stubs in these tests verify error classification, read-only transport,
authentication headers, the effective five-second deadline and mixed/fallback
paths. They are explicitly not live-backend acceptance evidence.

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
