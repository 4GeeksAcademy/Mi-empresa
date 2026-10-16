from datetime import date
from decimal import Decimal

import pytest

from data.process.business_kpis import calculate_business_kpis


def metric_row(rows, code, currency="XXX"):
    return next(row for row in rows if row["metric_code"] == code and row["currency_code"] == currency)


def test_calculates_five_kpis_and_keeps_cost_currencies_separate():
    rows = calculate_business_kpis(
        shipments=[
            {"shipment_id": "s1", "country_code": "US", "created_at": "2026-10-05T12:00:00Z", "promised_delivery_at": "2026-10-06T12:00:00Z"},
            {"shipment_id": "s2", "country_code": "US", "created_at": "2026-10-05T13:00:00Z", "promised_delivery_at": "2026-10-06T12:00:00Z"},
        ],
        delivery_events=[
            {"delivery_event_id": "d1", "shipment_id": "s1", "status": "delivered", "occurred_at": "2026-10-06T11:00:00Z"},
            {"delivery_event_id": "d2", "shipment_id": "s2", "status": "delivered", "occurred_at": "2026-10-06T13:00:00Z"},
        ],
        carrier_cost_lines=[
            {"cost_line_id": "c1", "country_code": "US", "accounting_date": "2026-10-06", "amount": "10", "currency_code": "USD", "status": "approved"},
            {"cost_line_id": "c2", "country_code": "US", "accounting_date": "2026-10-06", "amount": "2", "currency_code": "EUR", "status": "final"},
            {"cost_line_id": "c3", "country_code": "US", "accounting_date": "2026-10-06", "amount": "7", "currency_code": "GBP", "status": "final"},
            {"cost_line_id": "c4", "country_code": "US", "accounting_date": "2026-10-06", "amount": "99", "currency_code": "EUR", "status": "pending"},
        ],
        returns=[
            {"return_id": "r1", "country_code": "US", "status": "accepted", "accepted_at": "2026-10-06T15:00:00Z"},
            {"return_id": "r2", "country_code": "US", "status": "open", "created_at": "2026-10-06T16:00:00Z"},
            {"return_id": "r3", "country_code": "US", "status": "rejected", "created_at": "2026-10-06T16:00:00Z"},
        ],
        csat_responses=[
            {"response_id": "q1", "country_code": "US", "submitted_at": "2026-10-06T17:00:00Z", "score": 4, "scale_min": 1, "scale_max": 5, "is_valid": True},
            {"response_id": "q2", "country_code": "US", "submitted_at": "2026-10-06T18:00:00Z", "score": 5, "scale_min": 1, "scale_max": 5, "is_valid": True},
            {"response_id": "q3", "country_code": "US", "submitted_at": "2026-10-06T19:00:00Z", "score": 8, "scale_min": 0, "scale_max": 10, "is_valid": True},
        ],
        fx_rates=[{"rate_date": "2026-10-06", "base_currency": "USD", "quote_currency": "EUR", "rate": "0.9"}],
    )

    volume = metric_row(rows, "shipment_volume")
    assert volume["metric_date"] == date(2026, 10, 5)
    assert volume["metric_value"] == Decimal("2.000000")
    punctuality = metric_row(rows, "on_time_delivery_rate")
    assert punctuality["metric_value"] == Decimal("50.000000")
    assert (punctuality["numerator"], punctuality["denominator"]) == (Decimal("1.000000"), Decimal("2.000000"))
    cost_eur = metric_row(rows, "operating_cost_eur", "EUR")
    assert cost_eur["metric_value"] == Decimal("11.000000")
    cost_gbp = metric_row(rows, "operating_cost_eur", "GBP")
    assert (cost_gbp["metric_value"], cost_gbp["unit"]) == (Decimal("7.000000"), "GBP")
    assert metric_row(rows, "returns_count")["metric_value"] == Decimal("2.000000")
    csat = metric_row(rows, "customer_satisfaction_csat")
    assert (csat["metric_value"], csat["numerator"], csat["denominator"]) == (
        Decimal("4.500000"), Decimal("9.000000"), Decimal("2.000000")
    )


def test_duplicate_facts_are_deduplicated_or_rejected_if_conflicting():
    shipment = {"shipment_id": "s1", "country_code": "ES", "created_at": "2026-10-05T22:30:00Z"}
    rows = calculate_business_kpis(shipments=[shipment, shipment.copy()])
    assert len(rows) == 1
    assert rows[0]["metric_value"] == Decimal("1.000000")
    assert rows[0]["metric_date"] == date(2026, 10, 6)
    with pytest.raises(ValueError, match="Conflicting duplicate shipment_id"):
        calculate_business_kpis(shipments=[shipment, shipment | {"created_at": "2026-10-06T22:30:00Z"}])


def test_missing_sources_produce_no_kpis_and_invalid_csat_is_excluded():
    assert calculate_business_kpis() == []
    rows = calculate_business_kpis(
        csat_responses=[
            {"response_id": "q1", "country_code": "ES", "submitted_at": "2026-10-06T12:00:00Z", "score": 8, "scale_min": 0, "scale_max": 10, "is_valid": True}
        ]
    )
    assert rows == []
