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

Deploy `services/api/migrations/20261024_rfp_intake.sql` to PostgreSQL before running the API/worker. `data/raw` must be a shared durable volume for both services; Docker Compose mounts the workspace directory for local development. Install API dependencies from its project manifests for PDF conversion. Do not commit uploaded customer RFPs or credentials.

## Validation

Run `uv run --project services/api pytest services/api/tests/test_rfp.py tests/pipelines/test_rfp_intake.py`. The PDFs described in `trackflow-BRIEFING.es.md` must be uploaded through the UI against a running API, Redis worker, and PostgreSQL to verify the real end-to-end acceptance/rejection cases. These files are not preseeded in the repository.