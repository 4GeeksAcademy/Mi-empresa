from datetime import date
from decimal import Decimal

import pytest

from data.pipelines.pipeline import (
    calculate_carrier_cost_kpis,
    calculate_returns_csat_kpis,
    calculate_shipment_delivery_kpis,
)


def metric_row(rows, metric_code, currency_code="XXX"):
    return next(
        row
        for row in rows
        if row["metric_code"] == metric_code
        and row["currency_code"] == currency_code
    )


def test_shipment_volume_and_on_time_delivery_use_business_facts_in_memory():
    shipments = [
        {
            "shipment_id": "s1",
            "country_code": "US",
            "created_at": "2026-10-05T12:00:00Z",
            "promised_delivery_at": "2026-10-06T12:00:00Z",
        },
        {
            "shipment_id": "s2",
            "country_code": "US",
            "created_at": "2026-10-05T13:00:00Z",
            "promised_delivery_at": "2026-10-06T12:00:00Z",
        },
    ]
    delivery_events = [
        {
            "delivery_event_id": "d1",
            "shipment_id": "s1",
            "status": "delivered",
            "occurred_at": "2026-10-06T11:00:00Z",
        },
        {
            "delivery_event_id": "d2",
            "shipment_id": "s2",
            "status": "delivered",
            "occurred_at": "2026-10-06T13:00:00Z",
        },
    ]

    rows = calculate_shipment_delivery_kpis.fn(shipments, delivery_events)

    assert metric_row(rows, "shipment_volume")["metric_value"] == Decimal("2.000000")
    punctuality = metric_row(rows, "on_time_delivery_rate")
    assert punctuality["metric_date"] == date(2026, 10, 6)
    assert punctuality["metric_value"] == Decimal("50.000000")
    assert (punctuality["numerator"], punctuality["denominator"]) == (
        Decimal("1.000000"),
        Decimal("2.000000"),
    )


def test_carrier_costs_convert_with_approved_fx_and_keep_currency_units():
    rows = calculate_carrier_cost_kpis.fn(
        [
            {
                "cost_line_id": "c1",
                "country_code": "US",
                "accounting_date": "2026-10-06",
                "amount": "10",
                "currency_code": "USD",
                "status": "approved",
            },
            {
                "cost_line_id": "c2",
                "country_code": "US",
                "accounting_date": "2026-10-06",
                "amount": "2",
                "currency_code": "EUR",
                "status": "final",
            },
            {
                "cost_line_id": "c3",
                "country_code": "US",
                "accounting_date": "2026-10-06",
                "amount": "7",
                "currency_code": "GBP",
                "status": "final",
            },
        ],
        [
            {
                "rate_date": "2026-10-06",
                "base_currency": "USD",
                "quote_currency": "EUR",
                "rate": "0.9",
            }
        ],
    )

    assert metric_row(rows, "operating_cost_eur", "EUR")["metric_value"] == Decimal(
        "11.000000"
    )
    assert metric_row(rows, "operating_cost_eur", "GBP")["metric_value"] == Decimal(
        "7.000000"
    )


def test_returns_and_valid_csat_exclude_rejected_returns_and_invalid_scores():
    rows = calculate_returns_csat_kpis.fn(
        [
            {
                "return_id": "r1",
                "country_code": "ES",
                "status": "accepted",
                "accepted_at": "2026-10-06T15:00:00Z",
            },
            {
                "return_id": "r2",
                "country_code": "ES",
                "status": "rejected",
                "created_at": "2026-10-06T16:00:00Z",
            },
        ],
        [
            {
                "response_id": "q1",
                "country_code": "ES",
                "submitted_at": "2026-10-06T17:00:00Z",
                "score": 4,
                "scale_min": 1,
                "scale_max": 5,
                "is_valid": True,
            },
            {
                "response_id": "q2",
                "country_code": "ES",
                "submitted_at": "2026-10-06T18:00:00Z",
                "score": 8,
                "scale_min": 0,
                "scale_max": 10,
                "is_valid": True,
            },
        ],
    )

    assert metric_row(rows, "returns_count")["metric_value"] == Decimal("1.000000")
    assert metric_row(rows, "customer_satisfaction_csat")["metric_value"] == Decimal(
        "4.000000"
    )


def test_shipment_task_rejects_malformed_timestamp():
    with pytest.raises(ValueError, match="Invalid created_at"):
        calculate_shipment_delivery_kpis.fn(
            [{"shipment_id": "s1", "country_code": "US", "created_at": None}],
            [],
        )
