# TrackFlow Business Reporting

This service exposes the business-performance pipeline separately from technical telemetry.

## Run locally

From the repository root, install the API project and run the flow:

```bash
uv sync --project services/api
PREFECT_SERVER_ANALYTICS_ENABLED=false uv run --project services/api python data/pipelines/pipeline.py
```

When `DATABASE_URL` is absent, the CLI uses `data/process/business_reporting.sqlite3` for local run metadata and the proposed reporting tables. With `DATABASE_URL`, it creates the `reporting` schema and tables there. Configure an approved Prefect deployment named `trackflow_business_performance_flow/production` (or set `TRACKFLOW_REPORTING_DEPLOYMENT`) before using the manual API trigger.

The design proposes a five-minute refresh cadence and a seven-day rolling window. It is not an active schedule until a Prefect deployment and work pool are configured.

## Endpoints

- `GET /reporting/pipeline/status?run_id=<uuid>` returns run metadata; without `run_id`, it returns the latest run. Requires a manager or admin user.
- `POST /reporting/pipeline/runs` accepts `window_start`, exclusive `window_end`, and `country_codes` (`US`, `ES`); it enqueues the Prefect deployment and returns its run ID. Requires an admin user.
- `GET /reporting/kpis?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` reads the destination rows; `end_date` is exclusive. Optional filters are `country_code` and repeated `metric_codes`. Requires a manager or admin user.

KPI rows follow the proposed `reporting.business_kpis_daily` grain and fields from `data/pipelines/PIPELINE_DESIGN.md`. The pipeline creates `pipeline_runs`, `pipeline_checkpoints`, `pipeline_window_locks`, `pipeline_reprocess_queue`, and per-run staging tables in the same schema. Checkpoints advance only after publication; leases protect each date-window/country, and staging markers make empty complete partitions remove obsolete published rows atomically.

## Source availability

The flow reads `telemetry_events` only for reconciliation and does not write to it. Telemetry events and inventory orders do not prove shipments, delivery outcomes, carrier charges, accepted returns, or customer survey scores. The corresponding TMS, finance, reverse-logistics, CSAT, and FX connectors are not present in this repository. Until those sources are configured, runs record them as unavailable and do not publish or delete KPI partitions; they do not synthesize zeroes or sample data. When source facts are complete but a currency lacks an approved FX rate, costs remain in separate native-currency rows rather than being combined.