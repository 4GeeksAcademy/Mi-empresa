# `services` folder

This folder contains **all the backend services** (APIs and background workers) related to the company for the cross-functional AI Engineering project.

Each subfolder inside `services/` must correspond to **one specific service** (for example: `admin-api`, `data-processor-worker`) and include its own technical and functional documentation.

- **Main purpose**: to centralize all the backend logic, APIs, and queue consumers that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the services you add, their objective, the technology used, and how to run them.

## Services currently available

- `knowledge/` - Commercial knowledge corpus preparation and Qdrant indexing.
	See [configuration and current scope](knowledge/README.md).
- `api/` - FastAPI service for incidents analysis.
	- `POST /api/incidents/analyze`: validates and analyzes uploaded CSV files.
	- `GET /api/incidents/results/export`: exports the last analysis as `results.csv`.
	- `POST /suppliers`: creates a supplier.
	- `GET /suppliers`: lists suppliers with optional `pais` and `categoria` filters.
	- `PATCH /suppliers/{id}/rate`: updates supplier rate per kg.
	- `PATCH /suppliers/{id}/status`: updates supplier status.
	- `DELETE /suppliers/{id}`: removes supplier by id.

> _Spanish version: [README.es.md](./README.es.md)._

El análisis de eventos de telemetría de solo lectura vive en `telemetry/` y lo
consume `GET /telemetry/report` en `api/`.

## Desarrollo con Docker

El backend se inicia desde la raiz con `docker compose up` y queda disponible en
el puerto 8000. El contenedor ejecuta FastAPI con `--reload`; su configuracion de
desarrollo se carga desde el `.env` de la raiz.

El build usa contexto raiz para incluir el contrato de telemetria; desarrollo
lo monta readonly en `/docs/telemetry`. `POST /telemetry/events` valida cada
evento individualmente y persiste los validos por lote en Supabase.

## Nightly orchestration (DEV-53)

`job_runner.py` controls persistent `job_runs` state independently of FastAPI.
Apply `api/migrations/20261019_job_runs.sql` before running the standalone
`scripts/nightly_export.py`. Processing is the sole long-running exclusion
state; a short transaction makes acquisition and per-date idempotency atomic.
The module exposes create/acquire/finish/get operations, `has_processing_lock`
and `has_completed_for_date`. It never replaces the ETL's `pipeline_runs`.
`scripts/nightly_scheduler.py` uses APScheduler in its own process to launch
the export daily at 02:30 UTC. The optional Compose `scheduler` profile starts
that service without the API. See [operation, scheduler, tests and recovery](../scripts/README.md#dev-53-nightly-telemetry-export).
