# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

> _Spanish version: [README.es.md](./README.es.md)._

## Sales forecast model (`sales_forecast.py`)

Run: `uv run python scripts/sales_forecast.py` (seed 42; writes `docs/sales_forecast.png`). Test: `uv run pytest tests/pipelines/test_sales_split.py`.

- **Data/split**: `data/raw/trackflow_sales.csv` (`consolidated`, target `revenue_eur`). Train 2016-2023 (96 months), test 2024-2025 (24 months), temporal cut.
- **Features** (causal, scale-free, divided by revenue 12 months earlier): lags 1-3, rolling mean/std (3) and mean (12), month sin/cos, Nov-Dec and Feb flags. Same-month `shipments_processed` and `avg_revenue_per_shipment_eur` are excluded (they leak the target). No scaling is needed: trees are invariant to it and features are already ratios.
- **Model**: Random Forest. With 84 training rows it is stable without tuning, explainable (feature importances) and tree dispersion gives the variability band. XGBoost would be preferred with more data and time to tune. Target is the YoY ratio so the model can extrapolate growth beyond the train range.
- **Forecast**: recursive; test values are never used as inputs.
- **Metrics on test**: MSE/RMSE (average squared/typical error in EUR; a low MSE alone does not say if the error is small relative to revenue, if peaks are ranked right or if the model is stable, hence MAPE, Gini, K2 and PSI), PSI (shift between model score distributions in train and test; >0.25 means notable drift), normalized Gini (does the model rank high-revenue months above low ones; 1 = perfect), K2 (assumed to be R², share of variance explained).
- **Band**: P10-P90 across trees; it reflects model dispersion, not a full prediction interval.

## Regression model evaluation (`evaluate_regression_model.py`)

Run: `uv run python scripts/evaluate_regression_model.py`. Test: `uv run pytest tests/pipelines/test_cv_chronological.py`. Outputs and diagnosis are in `data/eval/` (`evaluation_report.md`, `learning_curve.png`, CSVs).

- Temporal CV (`TimeSeriesSplit`, 5 folds, 12-month validation windows) on the 2016-2023 train only; features are rebuilt per fold from that fold's training rows, and validation is a recursive forecast.
- Reports MAE/RMSE for train and validation as mean ± std, a learning curve, and a small hyperparameter comparison run with the same CV.

## DEV-53: nightly telemetry export

`nightly_export.py` is a standalone process, not a FastAPI background task. Install
the runtime dependencies from `services/api/requirements.txt` in the Python
environment used by the job. No API server, API authentication or HTTP call is
needed. The parent imports SQLAlchemy and `services/job_runner.py`, not FastAPI.

Before the first execution, apply
`services/api/migrations/20261019_job_runs.sql` using your normal database
migration procedure. It creates only `job_runs` and its indexes. The job does
not run migrations or create production tables automatically.

From the repository root, with the project environment active:

```bash
python scripts/nightly_export.py
TARGET_DATE=2026-10-18 python scripts/nightly_export.py
```

`DATABASE_URL` is required. Existing environment variables take precedence over
the root `.env`, loaded by an absolute path; no credentials are embedded in code
or cron. Use the database driver installed in your environment, for example
`postgresql+psycopg2://...` with the project's `psycopg2-binary` dependency.
Relative paths in a database URL remain the operator's responsibility; use an
absolute path for SQLite. Execution and output paths do not depend on cwd.

`TARGET_DATE` must be exactly `YYYY-MM-DD`; otherwise execution exits with code 1
before creating a run. Without it the target is yesterday's UTC calendar date.
The export selects `telemetry_events.timestamp` in `[00:00 UTC, next 00:00 UTC)`.
The existing timezone-naive timestamp column is treated as UTC; timezone-aware
columns use aware boundaries. All reflected columns are exported with headers,
ISO dates, JSON objects and CSV quoting. Empty dates produce a header-only CSV.

The output is `data/raw/telemetry_YYYY-MM-DD.csv`. A temporary file in the same
directory is flushed and published with a hard link that cannot overwrite an
existing file. This requires a local/POSIX filesystem supporting hard links.
Handled failures remove temporary files. A CSV already present is kept, even on
a retry; absence of a completed run still causes the pipeline to execute.

### State, locking and idempotency

`services/job_runner.py` persists `pending` before acquisition, then changes it
to `processing` before doing work. A short PostgreSQL transaction uses
`LOCK TABLE job_runs IN SHARE ROW EXCLUSIVE MODE` to serialize the processing
and completed checks with acquisition. That transaction ends before CSV or ETL
work; it is not a second long-running application lock. Only the persisted
`processing` row excludes other executions, globally by `job_name`, across dates.
An additional unique partial index on `job_name WHERE status = 'processing'`
enforces this invariant. SQLite uses `BEGIN IMMEDIATE` for local tests; its
database-wide writer serialization is not evidence of PostgreSQL concurrency.

The same transaction checks completed runs by `(job_name, target_date)` after
checking processing. No lock file, advisory lock, Redis or separate lock state
is used. The date index supports the idempotency query. Previous failed runs do
not prevent retries, and history is retained.

Successful work follows `pending -> processing -> completed`. Handled exceptions
follow `processing -> failed`, storing the exception message and `finished_at`.
Omitted invocations are audited as `pending -> failed`, with no `started_at` and
an `error_message` prefixed by `omitted:` (`processing lock` or `already completed
for date`). This deliberately uses the four required states rather than adding
`skipped` or falsely declaring work completed. Omission logs use INFO and exit 0;
actual failures use ERROR and exit 1. Operational queries should distinguish
`error_message LIKE 'omitted:%'` from real failures.

### Existing pipeline integration

The actual entry point is the public Prefect flow
`data.pipelines.pipeline.trackflow_business_performance_flow`. Its existing CLI
does not accept dates, so the job launches a small adapter in a separate process:

```text
<sys.executable> <absolute-root>/scripts/nightly_export.py --pipeline YYYY-MM-DD
```

The internal adapter passes `window_start=target_date`,
`window_end=target_date + 1 day` and `trigger='cli'` to the unchanged flow.
It returns nonzero when the flow returns a state other than `Completed`, even
without an exception. The parent checks the subprocess return code and declares
completed only after both export and flow succeed. No `--no-prefect` flag is
invented; this repository uses Prefect and needs its runtime dependencies. The
adapter is internal, not a scheduler entry point; operators run the normal job.

The CSV is backup/audit only. The flow continues reading telemetry directly
from the database for reconciliation and recording its own ETL metadata in
`reporting.pipeline_runs`. `job_runs` tracks nightly orchestration independently.
Missing authoritative business connectors remain an existing limitation: a
completed flow can publish zero KPI rows; this ticket does not fabricate data.

### Scheduling and logs

The primary trigger is **APScheduler 3.11.2 in a separate process**, implemented
in `scripts/nightly_scheduler.py`. It uses `BlockingScheduler` and an explicit UTC
`CronTrigger`: **02:30 UTC daily**, expression `30 2 * * *`, regardless of the host
timezone. It is never imported or started by FastAPI. Its callback launches
`nightly_export.py` through `sys.executable`, with an absolute path and explicit
repository working directory, without a shell. Only the script owns job state.

With the project Python environment active:

```bash
python scripts/nightly_scheduler.py --check
python scripts/nightly_scheduler.py
```

`--check` prints the cron expression, timezone and next firing time without
starting a daemon or connecting to a database. Normal startup requires
`DATABASE_URL`, loaded from the environment or the absolute root `.env` path.
Keep `TARGET_DATE` unset for scheduled runs; use it on the standalone exporter
for manual backfills. The scheduler must remain running under a process manager.

The optional Compose service has no dependency on the backend and exposes no
ports. After preparing the root `.env` and applying the SQL migration:

```bash
docker compose --profile scheduler up --build -d scheduler
docker compose logs -f scheduler
docker compose stop scheduler
```

The service uses the backend image with its command overridden, persists CSVs
through `./data/raw:/app/data/raw`, restarts unless stopped, and grants 40 seconds
for graceful shutdown. SIGTERM/SIGINT stop the scheduler, terminate any active
export process and let that process persist failed and reap its pipeline child.
A 25-second export shutdown deadline prevents indefinite scheduler shutdown;
forced termination still has the hard-kill limitations described below.

`max_instances=2` intentionally permits the next callback to launch a second
script, which then audits cancellation using the database processing state.
This setting is not the distributed lock. Multiple scheduler replicas still
coordinate through `job_runs`. Jobs are coalesced, with a one-hour misfire grace;
the in-memory schedule is rebuilt at startup and does not persist or replay all
missed dates after downtime. Backfill explicitly with `TARGET_DATE` when needed.

Scheduler configuration, real callback execution, subprocess exit handling,
graceful shutdown and the Docker image are verified. **Permanent deployment is
not activated here**: the root `.env` is absent, and the production job migration
has not been applied. No credentials or protected infrastructure were changed.

`scripts/nightly_export.crontab` remains an optional OS-cron alternative, not the
selected trigger. Never enable both accidentally. That alternative requires a
UTC cron host; its `TZ=UTC` assignment alone does not portably set daemon timezone.

Logs go to stderr/container logs; configure log retention in the deployment.
Every job log line has a UTC
timestamp, level, `job_name`, `target_date` and resulting `status`; child output is
wrapped with the same context. Normal start, completion and omissions use INFO;
exceptions use ERROR. Multiline exception messages keep context on each line.
Scheduler diagnostics also carry this context; their statuses describe scheduler
or subprocess events, not additional transitions in `job_runs`.

SIGINT/SIGTERM interrupt work, terminate and reap the child process group before
marking the run failed; repeated termination signals are ignored during cleanup.
SIGKILL, host failure, power loss and database unavailability cannot guarantee a
terminal update. If persistence fails, a separate ERROR explicitly requests
operator action; do not assume the recorded state changed. No stale-run timer
automatically releases processing: inspect the original process and children,
confirm they cannot still work, then have an authorized operator mark the run
failed with a reason and `finished_at`. Never release a potentially active run.
After hard crashes, inspect orphaned `.telemetry_*.tmp` files before deleting
them. PostgreSQL acquisition briefly locks the job table, so keep administrative
transactions short; it does not lock `telemetry_events` for the duration of ETL.

### Verification

Run only against an isolated local PostgreSQL database with `dev53` in its name:

```bash
TEST_JOB_DATABASE_URL='postgresql+psycopg2://USER:PASSWORD@127.0.0.1:PORT/dev53' \
	python -m pytest tests/pipelines/test_nightly_export.py -q
```

The tests create isolated schemas and apply the actual SQL migration, then
remove those schemas. The real-flow integration also writes ETL metadata to
`reporting` in that disposable database. It creates and removes future-date
CSV files in `data/raw`. Never supply a production database. With no test URL,
PostgreSQL checks are skipped, not considered verified.

Verified on 2026-10-19 using Python 3.14 and PostgreSQL 16: **35 passed, 1 skipped**
for this ticket, plus **4 existing pipeline tests passed** (39 passed total).
The skip is the SQLite variant of the real-flow integration, which is executed
on PostgreSQL. Tests cover UTC boundaries, malformed dates, JSON/CSV quoting,
temporary-file cleanup, all state transitions, duplicate dates, distinct dates,
cross-date locks, retries, pre-existing backups, actual nonzero child exit,
SIGTERM with child termination, and two spawned independent processes competing
on PostgreSQL. The real CLI runs from outside the repository and confirms separate
`job_runs`/`pipeline_runs` records and the exact one-day flow window.
The six APScheduler tests verify UTC calendar calculation, real scheduled callback
execution, subprocess success/failure, active-child shutdown and daemon SIGTERM.
The Docker image builds and its `--check` command succeeds on Python 3.12.
Compose validates using `docker compose --profile scheduler config
--no-env-resolution --quiet` without needing secrets; `uv lock --check` also passes.

End-to-end acceptance was also run in the Docker image against a separate,
disposable PostgreSQL 16 container with synthetic events only. It produced
`data/raw/telemetry_2026-10-18.csv` with exactly two of three fixtures; the third,
at `2026-10-19 00:00 UTC`, was excluded. `job_runs` reached `completed` with both
timestamps; `reporting.pipeline_runs` recorded the actual flow as `Completed`
with window `[2026-10-18, 2026-10-19)`. The retained CSV contains only synthetic
non-PII fixtures, not production telemetry, and is evidence of format/date-window
behavior rather than an operational backup or pipeline input. The temporary DB
is removed after validation. This verifies the CSV criterion with a non-empty,
inspectable artifact and does not imply production migration or scheduler
activation.

| Evaluation criterion | Evidence / status |
| --- | --- |
| Independent process and existing flow | Verified: real CLI/subprocess, no FastAPI import |
| State machine and timestamps | Verified on SQLite and PostgreSQL |
| Atomic processing lock | Verified with two independent competing processes on PostgreSQL |
| Idempotency by date | Verified: no second CSV or pipeline invocation |
| Failure cleanup and retry | Verified: export, pipeline failure and actual SIGTERM |
| CSV, UTC selection and TARGET_DATE | Verified: boundaries, quoting, invalid dates, existing CSV, retained synthetic end-to-end export |
| Separate orchestration / ETL metadata | Verified by real-flow PostgreSQL integration |
| Contextual logs | Verified in job tests and CLI output |
| Independent trigger | Verified: APScheduler UTC schedule, actual callback/subprocess, SIGTERM and Docker image; deployment activation pending |
| Production migration | SQL delivered and tested locally; deployment pending |

### PR draft

**Title:** DEV-53 - Independent APScheduler and nightly telemetry export

**Summary:** Add a standalone nightly job, SQL migration and state service.
Acquire processing atomically in a short job-table transaction, backed by a
unique partial processing index; retain per-date completed-run idempotency and
audit omissions without adding states. Export an immutable UTC-day CSV and
launch the existing Prefect flow through a dated subprocess adapter. Keep
`job_runs` separate from `reporting.pipeline_runs`; the flow reads BD, not CSV.

**Schedule:** APScheduler in a dedicated process/optional Compose service,
`30 2 * * *`, 02:30 UTC explicitly. Chosen to avoid a host cron dependency and keep
nightly orchestration independent of FastAPI. The callback starts a subprocess;
processing in BD remains the distributed lock. Cron is only an optional fallback.

**Validation:** 39 passed including existing pipeline regression tests, and 1
intentionally skipped SQLite integration case; PostgreSQL concurrency, real
CLI/flow, APScheduler callback and SIGTERM cleanup verified locally. Docker
build/check, Compose configuration and dependency lock check also pass.

**Deployment / risks:** Apply SQL migration, install project dependencies and
start the dedicated scheduler service with DATABASE_URL configured. Production
migration and permanent scheduler activation are pending. Hard kills or database outages require operator
reconciliation, not automatic lock release. Existing missing business sources
still prevent publication of real business KPIs.
