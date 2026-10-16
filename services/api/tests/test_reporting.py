from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from prefect.states import Failed
from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, select, update

import auth
from data.pipelines import pipeline
from main import app
from services.reporting import routes as reporting_routes


@pytest.fixture
def reporting_client(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'reporting.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    pipeline.get_reporting_engine.cache_clear()
    app.dependency_overrides[auth.get_current_user] = lambda: {"id": 21, "role": "manager"}
    app.dependency_overrides[auth.get_current_admin] = lambda: {"id": 1, "role": "admin"}
    client = TestClient(app)
    yield client
    client.close()
    app.dependency_overrides.clear()
    pipeline.get_reporting_engine.cache_clear()


def test_flow_records_run_and_tolerates_optional_source_failure(reporting_client, monkeypatch):
    requested_run_id = str(uuid4())

    class FailedOptionalTask:
        def __call__(self, window_start, window_end, *, return_state=False):
            assert return_state is True
            return Failed(message="optional source unavailable")

    monkeypatch.setattr(pipeline, "extract_source_batch", FailedOptionalTask())
    result = pipeline.trackflow_business_performance_flow(
        date(2026, 10, 1), date(2026, 10, 8), ["US", "ES"], run_id=requested_run_id
    )

    assert result["run_id"] == requested_run_id
    assert result["state"] == "Completed"
    assert result["rows_written"] == 0
    assert result["error_code"] == "OPTIONAL_TELEMETRY_UNAVAILABLE"
    status_response = reporting_client.get(
        "/reporting/pipeline/status", params={"run_id": result["run_id"]}
    )
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "Completed"
    assert status_response.json()["finished_at"] is not None


def test_partition_publish_replaces_existing_rows_idempotently(reporting_client):
    base_row = {
        "metric_date": date(2026, 10, 5),
        "country_code": "US",
        "metric_code": "shipment_volume",
        "currency_code": "XXX",
        "metric_value": 3,
        "numerator": 3,
        "denominator": None,
        "unit": "shipments",
        "source_watermark": datetime(2026, 10, 6, tzinfo=timezone.utc),
        "refreshed_at": datetime(2026, 10, 6, tzinfo=timezone.utc),
        "definition_version": 1,
        "run_id": str(uuid4()),
    }
    partition = [(date(2026, 10, 5), "US")]
    first_run_id = str(uuid4())
    pipeline.stage_reporting_partition.fn(
        [base_row], partition, datetime(2026, 10, 6, tzinfo=timezone.utc), first_run_id
    )
    pipeline.publish_reporting_partition.fn(first_run_id)
    updated_row = base_row | {"metric_value": 4, "numerator": 4, "run_id": str(uuid4())}
    second_run_id = str(uuid4())
    pipeline.stage_reporting_partition.fn(
        [updated_row], partition, datetime(2026, 10, 6, tzinfo=timezone.utc), second_run_id
    )
    pipeline.publish_reporting_partition.fn(second_run_id)

    rows = pipeline.query_business_kpis(date(2026, 10, 5), date(2026, 10, 6))
    assert len(rows) == 1
    assert rows[0]["metric_value"] == 4

    empty_run_id = str(uuid4())
    pipeline.stage_reporting_partition.fn(
        [], partition, datetime(2026, 10, 7, tzinfo=timezone.utc), empty_run_id
    )
    assert pipeline.publish_reporting_partition.fn(empty_run_id) == 0
    assert pipeline.query_business_kpis(date(2026, 10, 5), date(2026, 10, 6)) == []


def test_reporting_endpoints_enqueue_and_return_kpi_contract(reporting_client, monkeypatch):
    deployment_run_id = uuid4()
    enqueued_parameters = {}

    async def fake_run_deployment(name, **kwargs):
        assert name == "trackflow_business_performance_flow/production"
        assert kwargs["timeout"] == 0
        enqueued_parameters.update(kwargs["parameters"])
        return SimpleNamespace(id=deployment_run_id)

    monkeypatch.setattr(reporting_routes, "run_deployment", fake_run_deployment)
    queued = reporting_client.post(
        "/reporting/pipeline/runs",
        json={"window_start": "2026-10-01", "window_end": "2026-10-08", "country_codes": ["US"]},
    )
    assert queued.status_code == 202
    expected_run_id = queued.json()["run_id"]
    assert expected_run_id != str(deployment_run_id)
    assert enqueued_parameters["run_id"] == expected_run_id
    assert queued.json() == {"run_id": expected_run_id, "state": "Scheduled"}
    scheduled_status = reporting_client.get(
        "/reporting/pipeline/status", params={"run_id": expected_run_id}
    )
    assert scheduled_status.status_code == 200
    assert scheduled_status.json()["state"] == "Scheduled"

    row = {
        "metric_date": date(2026, 10, 5),
        "country_code": "US",
        "metric_code": "shipment_volume",
        "currency_code": "XXX",
        "metric_value": 3,
        "numerator": 3,
        "denominator": None,
        "unit": "shipments",
        "source_watermark": datetime(2026, 10, 6, tzinfo=timezone.utc),
        "refreshed_at": datetime(2026, 10, 6, tzinfo=timezone.utc),
        "definition_version": 1,
        "run_id": str(uuid4()),
    }
    with pipeline.get_reporting_engine().begin() as connection:
        connection.execute(insert(pipeline.business_kpis_daily).values(row))

    response = reporting_client.get(
        "/reporting/kpis",
        params={"start_date": "2026-10-01", "end_date": "2026-10-08", "country_code": "US"},
    )
    assert response.status_code == 200
    metric = response.json()["metrics"][0]
    assert metric["metric_date"] == "2026-10-05"
    assert metric["country_code"] == "US"
    assert metric["metric_code"] == "shipment_volume"
    assert metric["currency_code"] == "XXX"
    assert metric["metric_value"] == "3.000000"
    assert metric["numerator"] == "3.000000"
    assert metric["denominator"] is None
    assert metric["unit"] == "shipments"
    assert metric["definition_version"] == 1


def test_reporting_reads_reject_regular_users(reporting_client):
    app.dependency_overrides[auth.get_current_user] = lambda: {"id": 8, "role": "user"}

    status_response = reporting_client.get("/reporting/pipeline/status")
    kpis_response = reporting_client.get(
        "/reporting/kpis",
        params={"start_date": "2026-10-01", "end_date": "2026-10-08"},
    )

    assert status_response.status_code == 403
    assert kpis_response.status_code == 403


def test_failed_enqueue_is_persisted_as_failed_run(reporting_client, monkeypatch):
    run_id = str(uuid4())
    monkeypatch.setattr(reporting_routes, "uuid4", lambda: run_id)

    async def fail_enqueue(*args, **kwargs):
        raise RuntimeError("prefect unavailable")

    monkeypatch.setattr(reporting_routes, "run_deployment", fail_enqueue)
    response = reporting_client.post(
        "/reporting/pipeline/runs",
        json={"window_start": "2026-10-01", "window_end": "2026-10-08", "country_codes": ["US"]},
    )

    assert response.status_code == 503
    status_response = reporting_client.get(
        "/reporting/pipeline/status", params={"run_id": run_id}
    )
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "Failed"
    assert status_response.json()["error_code"] == "PREFECT_ENQUEUE_FAILED"


def test_flow_only_reads_telemetry_events(reporting_client):
    telemetry_events = Table(
        "telemetry_events",
        MetaData(),
        Column("id", String, primary_key=True),
        Column("timestamp", DateTime(timezone=True), nullable=False),
        Column("event_type", String, nullable=False),
    )
    engine = pipeline.get_reporting_engine()
    telemetry_events.create(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(telemetry_events).values(
                id=str(uuid4()),
                timestamp=datetime(2026, 10, 5, 12, tzinfo=timezone.utc),
                event_type="inbound_order_created",
            )
        )

    result = pipeline.trackflow_business_performance_flow(
        date(2026, 10, 1), date(2026, 10, 8), ["US"]
    )

    with engine.connect() as connection:
        stored_events = connection.execute(select(telemetry_events)).all()
    assert result["rows_read"] == 1
    assert result["rows_written"] == 0
    assert len(stored_events) == 1
    assert pipeline.calculate_kpis.cache_key_fn is not None
    assert pipeline.calculate_kpis.cache_expiration.total_seconds() == 600
    assert pipeline.extract_source_batch.retries > 0


def test_unavailable_business_sources_do_not_erase_published_kpis(reporting_client):
    row = {
        "metric_date": date(2026, 10, 5),
        "country_code": "US",
        "metric_code": "shipment_volume",
        "currency_code": "XXX",
        "metric_value": 4,
        "numerator": 4,
        "denominator": None,
        "unit": "shipments",
        "source_watermark": datetime(2026, 10, 6, tzinfo=timezone.utc),
        "refreshed_at": datetime(2026, 10, 6, tzinfo=timezone.utc),
        "definition_version": 1,
        "run_id": str(uuid4()),
    }
    with pipeline.get_reporting_engine().begin() as connection:
        connection.execute(insert(pipeline.business_kpis_daily).values(row))

    result = pipeline.trackflow_business_performance_flow(
        date(2026, 10, 1), date(2026, 10, 8), ["US"]
    )

    rows = pipeline.query_business_kpis(date(2026, 10, 5), date(2026, 10, 6))
    assert result["state"] == "Completed"
    assert rows[0]["metric_value"] == 4


def test_window_lease_blocks_overlap_and_can_be_reclaimed_after_expiry(reporting_client):
    start = date(2026, 10, 1)
    end = date(2026, 10, 8)
    owner_run_id = str(uuid4())
    competing_run_id = str(uuid4())
    assert pipeline.acquire_window_locks.fn(owner_run_id, start, end, ["US"])
    assert not pipeline.acquire_window_locks.fn(competing_run_id, start, end, ["US"])

    with pipeline.get_reporting_engine().begin() as connection:
        connection.execute(update(pipeline.pipeline_window_locks).values(
            lease_expires_at=datetime(2026, 10, 1, tzinfo=timezone.utc)
        ))
    assert pipeline.acquire_window_locks.fn(competing_run_id, start, end, ["US"])
    pipeline.release_window_locks.fn(competing_run_id)


def test_checkpoint_and_reprocess_queue_are_persistent_and_idempotent(reporting_client):
    run_id = str(uuid4())
    metric_date = date(2026, 10, 5)
    pipeline.enqueue_reprocess_item.fn("shipping.shipments", "US", metric_date, "late fact")
    pipeline.enqueue_reprocess_item.fn("shipping.shipments", "US", metric_date, "corrected fact")
    assert pipeline.claim_reprocess_items.fn(
        run_id, metric_date, date(2026, 10, 6), ["US"]
    ) == 1
    pipeline.commit_source_checkpoint.fn(
        "shipping.shipments", "US", datetime(2026, 10, 5, tzinfo=timezone.utc),
        "shipment-10", datetime(2026, 10, 6, tzinfo=timezone.utc), run_id,
    )
    pipeline.complete_reprocess_items.fn(run_id)

    with pipeline.get_reporting_engine().connect() as connection:
        checkpoint = connection.execute(select(pipeline.pipeline_checkpoints)).one()
        queue_item = connection.execute(select(pipeline.pipeline_reprocess_queue)).one()
    assert checkpoint.last_successful_run_id == run_id
    assert queue_item.status == "Completed"
    assert queue_item.reason == "corrected fact"