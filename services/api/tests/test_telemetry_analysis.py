from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

import cache as cache_module
import routes.telemetry as telemetry_routes
from models import TelemetryEventRecord
from services.telemetry import analysis


@pytest.fixture
def telemetry_engine(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TelemetryEventRecord.__table__.create(engine)
    monkeypatch.setattr(analysis, "get_engine", lambda: engine)
    yield engine
    engine.dispose()


@pytest.fixture
def report_client():
    app = FastAPI()
    app.include_router(telemetry_routes.router)
    telemetry_routes.report_cache.clear()
    yield TestClient(app)
    telemetry_routes.report_cache.clear()


def add_event(engine, timestamp, event_type, tags=None):
    with Session(engine) as session:
        session.add(
            TelemetryEventRecord(
                id=uuid4(),
                timestamp=timestamp,
                service="api",
                event_type=event_type,
                tags=tags or {},
            )
        )
        session.commit()


def test_database_boundaries_are_normalized_to_naive_utc():
    value = datetime(2026, 10, 1, 2, tzinfo=timezone(timedelta(hours=2)))

    assert analysis._utc_database_boundary(value) == datetime(2026, 10, 1)
    with pytest.raises(ValueError):
        analysis._utc_database_boundary(datetime(2026, 10, 1))


def test_events_per_day_uses_utc_and_inclusive_exclusive_bounds(telemetry_engine):
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 3, tzinfo=timezone.utc)
    add_event(telemetry_engine, start, "login_succeeded")
    add_event(
        telemetry_engine,
        datetime(2026, 10, 1, 23, tzinfo=timezone.utc),
        "login_succeeded",
    )
    add_event(telemetry_engine, end, "login_failed")

    result = analysis.events_per_day(start, end)

    assert json.loads(json.dumps(result)) == result
    assert result == [
        {"date": "2026-10-01", "event_type": "login_succeeded", "event_count": 2}
    ]
    converted = analysis._add_utc_date(
        pd.DataFrame(
            {
                "timestamp": ["2026-10-02T01:00:00+02:00"],
                "event_type": ["login_succeeded"],
            }
        )
    )
    assert converted.loc[0, "date"] == "2026-10-01"


def test_error_rate_by_type_uses_observed_latency_denominator(telemetry_engine):
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 2, tzinfo=timezone.utc)
    add_event(telemetry_engine, start, "api_latency_recorded", {"route": "/health"})
    add_event(
        telemetry_engine,
        start + timedelta(minutes=1),
        "api_latency_recorded",
        {"route": "/health"},
    )
    add_event(
        telemetry_engine,
        start + timedelta(minutes=2),
        "api_error_recorded",
        {"error_code": "server_error"},
    )
    add_event(
        telemetry_engine,
        start,
        "frontend_error_captured",
        {"error_code": "javascript_error"},
    )

    result = analysis.error_rate_by_type(start, end)

    assert json.loads(json.dumps(result)) == result
    assert result == [
        {
            "date": "2026-10-01",
            "error_code": "server_error",
            "error_count": 1,
            "observed_request_count": 2,
            "error_rate": 0.5,
        }
    ]


def test_latency_by_endpoint_averages_valid_samples(telemetry_engine):
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 2, tzinfo=timezone.utc)
    add_event(telemetry_engine, start, "api_latency_recorded", {"route": "/health", "duration_ms": 100})
    add_event(
        telemetry_engine,
        start + timedelta(minutes=1),
        "api_latency_recorded",
        {"route": "/health", "duration_ms": 300},
    )
    add_event(telemetry_engine, start, "api_latency_recorded", {"route": "/unknown"})
    add_event(telemetry_engine, end, "api_latency_recorded", {"route": "/health", "duration_ms": 900})

    result = analysis.latency_by_endpoint(start, end)

    assert json.loads(json.dumps(result)) == result
    assert result == [
        {
            "date": "2026-10-01",
            "route": "/health",
            "mean_latency_ms": 200.0,
            "sample_count": 2,
        }
    ]


def test_queries_project_columns_and_filter_in_sql(telemetry_engine):
    statements = []

    @sqlalchemy_event.listens_for(telemetry_engine, "before_cursor_execute")
    def capture_sql(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(" ".join(statement.upper().split()))

    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 2, tzinfo=timezone.utc)
    analysis.events_per_day(start, end)
    analysis.latency_by_endpoint(start, end)

    assert len(statements) == 2
    assert all("TELEMETRY_EVENTS.TIMESTAMP >=" in statement for statement in statements)
    assert all("TELEMETRY_EVENTS.TIMESTAMP <" in statement for statement in statements)
    assert "SELECT TELEMETRY_EVENTS.TIMESTAMP, TELEMETRY_EVENTS.EVENT_TYPE FROM" in statements[0]
    assert "SELECT *" not in " ".join(statements)
    assert "TELEMETRY_EVENTS.EVENT_TYPE IN" in statements[1]


def test_report_endpoint_normalizes_period_and_returns_expected_structure(report_client, monkeypatch):
    metric_calls = []

    def metric(name):
        def calculate(start_date, end_date):
            metric_calls.append((name, start_date, end_date))
            return [{"metric": name}]

        return calculate

    monkeypatch.setattr(telemetry_routes, "events_per_day", metric("events"))
    monkeypatch.setattr(telemetry_routes, "error_rate_by_type", metric("errors"))
    monkeypatch.setattr(telemetry_routes, "latency_by_endpoint", metric("latency"))
    response = report_client.get(
        "/telemetry/report?start_date=2026-10-01T02:00:00%2B02:00&end_date=2026-10-02T00:00:00Z"
    )

    assert response.status_code == 200
    assert response.json() == {
        "period": {"from": "2026-10-01T00:00:00+00:00", "to": "2026-10-02T00:00:00+00:00"},
        "metrics": {
            "events_per_day": [{"metric": "events"}],
            "error_rate_by_type": [{"metric": "errors"}],
            "latency_by_endpoint": [{"metric": "latency"}],
        },
    }
    assert len(metric_calls) == 3
    assert all(
        call[1:] == (datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 2, tzinfo=timezone.utc))
        for call in metric_calls
    )


def test_report_defaults_to_last_seven_days(report_client, monkeypatch):
    fixed_now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now.astimezone(tz) if tz else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(telemetry_routes, "datetime", FixedDateTime)
    monkeypatch.setattr(telemetry_routes, "events_per_day", lambda *_: [])
    monkeypatch.setattr(telemetry_routes, "error_rate_by_type", lambda *_: [])
    monkeypatch.setattr(telemetry_routes, "latency_by_endpoint", lambda *_: [])

    response = report_client.get("/telemetry/report")

    assert response.status_code == 200
    assert response.json()["period"] == {
        "from": "2026-10-01T12:00:00+00:00",
        "to": "2026-10-08T12:00:00+00:00",
    }


@pytest.mark.parametrize(
    "query",
    [
        "?start_date=not-a-date",
        "?start_date=2026-10-02T00:00:00Z&end_date=2026-10-01T00:00:00Z",
        "?start_date=2026-10-01T00:00:00&end_date=2026-10-02T00:00:00Z",
    ],
)
def test_report_rejects_invalid_periods(report_client, query):
    assert report_client.get(f"/telemetry/report{query}").status_code == 422


def test_report_caches_same_parameters_for_sixty_seconds(monkeypatch):
    telemetry_routes.report_cache.clear()
    clock = [100.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock[0])
    calls = []

    def metric(name):
        def calculate(*_):
            calls.append(name)
            return []

        return calculate

    monkeypatch.setattr(telemetry_routes, "events_per_day", metric("events"))
    monkeypatch.setattr(telemetry_routes, "error_rate_by_type", metric("errors"))
    monkeypatch.setattr(telemetry_routes, "latency_by_endpoint", metric("latency"))
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 2, tzinfo=timezone.utc)

    first = telemetry_routes.telemetry_report(start, end)
    assert telemetry_routes.telemetry_report(start, end) == first
    assert len(calls) == 3

    clock[0] += 60.1
    telemetry_routes.telemetry_report(start, end)
    assert len(calls) == 6