# RFP Intake — Part 1

## Processing flow

The Celery task first converts the uploaded PDF into a persisted Markdown file.
Only that Markdown is passed to the LangGraph in `services/rfp_graph.py`:

1. Classify customer RFP vs. carrier-sales pitch.
2. Extract shared metadata and readability metrics.
3. Fan out with LangGraph `Send` to one isolated node per required department
	(`warehouse`, `lastmile`, `reverse`). Each node receives Markdown and metadata,
	extracts only its scope, and reports missing information as open questions.
4. Join at the synthesizer and emit the Part 2 handoff referencing the Markdown,
	so downstream processing need not parse the PDF again.

Department nodes currently use deterministic heuristics; they are real parallel
graph workers but are not LLM-backed agent personas. The approvers are routing
owners (`warehouse`: Ana Whitfield, `lastmile`: Carlos Vega, `reverse`: Sofía
Ramos), not separately deployed Celery services.

## Verification

Focused checks: `uv run --project services/api pytest tests/pipelines/test_rfp_intake.py tests/pipelines/test_rfp_graph.py services/api/tests/test_rfp.py -q`.
Live verification still requires applying the PostgreSQL migration, running the
API/worker/Redis stack, and uploading the three source PDFs from the RFP brief.
# TrackFlow RFP intake (Part 1)

The backoffice **Recepción de RFPs** page uploads a PDF to the existing FastAPI backend. `POST /api/rfps` stores the raw artifact under `data/raw/rfps/<owner>/`, persists a PostgreSQL/SQLModel ticket, and queues only its identifier on the existing Celery/Redis worker. The worker converts the PDF to Markdown before classification (`MarkItDown` with `pdfminer.six` fallback), computes simple text legibility metrics, and persists the result and any handoff data. The API's `GET /api/rfps/{ticket_id}` is owner-scoped and can be polled while analysis is pending.

Tickets use the Part 1 states `analizando`, `descartado`, and `analisis_completo`. A technical processing failure leaves the business state visible and stores a non-sensitive `processing_error` diagnostic for support; it is not mislabeled as a rejected RFP. The JSON `synthesizer_payload` contains the ticket id, metadata, active department workstreams, and Markdown artifact reference for the next stage. The original PDF and Markdown remain runtime artifacts, not the source of truth for ticket state.

Department routing is limited to `warehouse` (Ana Whitfield), `lastmile` (Carlos Vega), and `reverse` (Sofía Ramos). Missing values remain null and department workstreams include open questions where appropriate. The current classifier and field extraction are deterministic, rule-based baseline logic; extend them with evaluated extraction/classification models without silently filling unknown values. Unknown service terms are explicitly represented in metadata for future extractor extensions.

Deploy `services/api/migrations/20261024_rfp_intake.sql` and then
`services/api/migrations/20261112_rfp_sse_acceptance.sql` to PostgreSQL before
running the API/worker. The latter adds the durable `accepted_at` timestamp and
owner/cursor index used by SSE and reconnect recovery. Apply it before deploying
the updated API or worker to an existing database. `data/raw` must be a shared
durable volume for both services; Docker Compose mounts the workspace directory
for local development. Install API dependencies from its project manifests for
PDF conversion. Do not commit uploaded customer RFPs or credentials.

## Real-time arrival notifications (SSE)

The authenticated `GET /api/rfps/events?since=<ISO-8601>` endpoint emits
`event: rfp_ticket_created` only after the classifier has accepted the document
as an RFP. The worker persists `classification_result=true` and `accepted_at`
atomically with the extracted metadata; uploads still pending classification
and rejected carrier pitches are not eligible. `accepted_at` is the event time
and recovery cursor, so a ticket uploaded before the dashboard opened but
accepted afterwards is still notified.
Its `data:` JSON follows `sistemas-en-tiempo-real-BRIEFING.es.md`: `ticket_id`,
`rfp_id`, `client_name`, `client_country`, `services_requested`, initial
`status: "analyzing"`, and `created_at`. It deliberately excludes the PDF,
filename, department extracts, and handoff. The stored legacy API status is
`analizando`; only the SSE boundary uses the briefing's required event value.
The stream queries the durable, owner-scoped SQL ticket table once per second,
sends a comment keep-alive every 15 seconds, and does not depend on one API
process or Redis Pub/Sub state.

The backoffice uses `fetch` with the existing bearer JWT and reads the response
stream. It snapshots `GET /api/rfps?created_after=<page-open-time>` before every
stream connection/reconnection; the cutoff is evaluated against `accepted_at`,
recovering RFPs accepted while offline (even if uploaded earlier). The same
cutoff is sent to SSE, making snapshot/live overlap intentional and
safe: the UI deduplicates by `ticket_id`. Retries use exponential backoff from
500 ms up to 30 seconds. Existing detail polling remains only for the ticket
currently being analyzed; arrival notifications and missed-arrival recovery do
not depend on polling.

Each dashboard has an independent SSE connection. At 50 open dashboards this
means 50 active HTTP streams and approximately 50 lightweight SQL polling reads
per second per API process (plus recovery snapshots at connect). That is
reasonable for this initial scale but should be measured; for larger fan-out,
replace per-client database polling with a shared wake-up mechanism such as
PostgreSQL notifications or Redis Streams, while retaining SQL snapshots as the
recovery source of truth. Do not rely on ephemeral Pub/Sub alone for replay.

SSE fits because ticket arrival is a one-way server-to-dashboard notification
over HTTP, with native streaming, simple infrastructure, and browser fetch
support for bearer auth. WebSockets become appropriate if the dashboard needs
interactive two-way actions on the same low-latency channel (for example,
claiming or routing a ticket live); those actions still require normal auth,
authorization, persistence, and idempotency checks.

### Manual reconnect and deduplication check

1. Sign into the backoffice and open `/rfps`; confirm the Network panel shows
	`/api/rfps/events` with `text/event-stream` and a bearer-authenticated request.
2. Disconnect the browser in DevTools Network throttling (Offline). From a
	second authenticated session, upload a valid PDF to create a ticket.
3. Restore connectivity. Confirm the request retries with a delay, the snapshot
	recovery displays the new ticket without a page reload, and the stream
	resumes. The ticket should appear exactly once even if snapshot and SSE both
	return it.
4. Repeat with an invalid/expired token: the SSE proxy/API must return 401, not
	an event stream.

## Validation

Run `uv run --project services/api pytest services/api/tests/test_rfp.py tests/pipelines/test_rfp_intake.py`. The PDFs described in `trackflow-BRIEFING.es.md` must be uploaded through the UI against a running API, Redis worker, and PostgreSQL to verify the real end-to-end acceptance/rejection cases. These files are not preseeded in the repository.