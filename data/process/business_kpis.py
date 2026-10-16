from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable
from zoneinfo import ZoneInfo

COUNTRY_TIMEZONES = {
    "US": ZoneInfo("America/Los_Angeles"),
    "ES": ZoneInfo("Europe/Madrid"),
}
METRIC_UNITS = {
    "shipment_volume": "shipments",
    "on_time_delivery_rate": "percent",
    "operating_cost_eur": "EUR",
    "returns_count": "returns",
    "customer_satisfaction_csat": "score_1_5",
}
SIX_PLACES = Decimal("0.000001")


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid {field}") from exc
    if not result.is_finite():
        raise ValueError(f"Invalid {field}")
    return result


def _timestamp(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid {field}") from exc
    else:
        raise ValueError(f"Invalid {field}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _business_date(value: Any, country_code: str, field: str) -> date:
    try:
        local_timezone = COUNTRY_TIMEZONES[country_code]
    except KeyError as exc:
        raise ValueError("country_code must be US or ES") from exc
    return _timestamp(value, field).astimezone(local_timezone).date()


def _unique_records(records: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    unique: dict[Any, dict[str, Any]] = {}
    for record in records:
        identifier = record.get(key)
        if identifier is None:
            raise ValueError(f"Missing {key}")
        previous = unique.get(identifier)
        if previous is not None and previous != record:
            raise ValueError(f"Conflicting duplicate {key}")
        unique[identifier] = record
    return list(unique.values())


def calculate_business_kpis(
    *,
    shipments: Iterable[dict[str, Any]] = (),
    delivery_events: Iterable[dict[str, Any]] = (),
    carrier_cost_lines: Iterable[dict[str, Any]] = (),
    returns: Iterable[dict[str, Any]] = (),
    csat_responses: Iterable[dict[str, Any]] = (),
    fx_rates: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Aggregate normalized facts without inferring data from missing sources."""
    totals: defaultdict[tuple[date, str, str, str], dict[str, Decimal]] = defaultdict(
        lambda: {"numerator": Decimal(0), "denominator": Decimal(0)}
    )
    shipment_index: dict[Any, dict[str, Any]] = {}
    shipment_ids: defaultdict[tuple[date, str], set[Any]] = defaultdict(set)

    for shipment in _unique_records(shipments, "shipment_id"):
        shipment_id = shipment["shipment_id"]
        country = shipment.get("country_code")
        metric_date = _business_date(shipment.get("created_at"), country, "created_at")
        shipment_index[shipment_id] = shipment
        shipment_ids[(metric_date, country)].add(shipment_id)

    for (metric_date, country), identifiers in shipment_ids.items():
        totals[(metric_date, country, "shipment_volume", "XXX")]["numerator"] = Decimal(len(identifiers))

    delivered_at_by_shipment: dict[Any, datetime] = {}
    for event in _unique_records(delivery_events, "delivery_event_id"):
        if str(event.get("status", "")).lower() != "delivered":
            continue
        shipment_id = event.get("shipment_id")
        if shipment_id not in shipment_index:
            continue
        delivered_at = _timestamp(event.get("occurred_at"), "occurred_at")
        previous = delivered_at_by_shipment.get(shipment_id)
        if previous is None or delivered_at < previous:
            delivered_at_by_shipment[shipment_id] = delivered_at

    for shipment_id, delivered_at in delivered_at_by_shipment.items():
        shipment = shipment_index[shipment_id]
        promised_value = shipment.get("promised_delivery_at")
        if promised_value is None:
            continue
        promised_at = _timestamp(promised_value, "promised_delivery_at")
        country = shipment["country_code"]
        metric_date = delivered_at.astimezone(COUNTRY_TIMEZONES[country]).date()
        aggregate = totals[(metric_date, country, "on_time_delivery_rate", "XXX")]
        aggregate["denominator"] += 1
        if delivered_at <= promised_at:
            aggregate["numerator"] += 1

    rates: dict[tuple[date, str], Decimal] = {}
    for rate in fx_rates:
        rate_date = date.fromisoformat(str(rate["rate_date"]))
        base_currency = str(rate["base_currency"]).upper()
        quote_currency = str(rate["quote_currency"]).upper()
        if quote_currency != "EUR":
            raise ValueError("FX quote_currency must be EUR")
        rate_key = (rate_date, base_currency)
        rate_value = _decimal(rate.get("rate"), "rate")
        if rate_value <= 0:
            raise ValueError("FX rate must be positive")
        if rate_key in rates and rates[rate_key] != rate_value:
            raise ValueError("Conflicting FX rate for date and currency")
        rates[rate_key] = rate_value

    for line in _unique_records(carrier_cost_lines, "cost_line_id"):
        if str(line.get("status", "")).lower() not in {"approved", "final"}:
            continue
        country = line.get("country_code")
        accounting_date = date.fromisoformat(str(line.get("accounting_date")))
        source_currency = str(line.get("currency_code", "")).upper()
        amount = _decimal(line.get("amount"), "amount")
        fx_rate = Decimal(1) if source_currency == "EUR" else rates.get((accounting_date, source_currency))
        output_currency = "EUR" if fx_rate is not None else source_currency
        output_amount = amount * fx_rate if fx_rate is not None else amount
        totals[(accounting_date, country, "operating_cost_eur", output_currency)]["numerator"] += output_amount

    for return_record in _unique_records(returns, "return_id"):
        state = str(return_record.get("status", "")).lower()
        if state not in {"accepted", "open"}:
            continue
        country = return_record.get("country_code")
        event_time = return_record.get("accepted_at") or return_record.get("created_at")
        metric_date = _business_date(event_time, country, "accepted_at/created_at")
        totals[(metric_date, country, "returns_count", "XXX")]["numerator"] += 1

    for response in _unique_records(csat_responses, "response_id"):
        if response.get("is_valid") is not True:
            continue
        score = _decimal(response.get("score"), "score")
        scale_min = _decimal(response.get("scale_min"), "scale_min")
        scale_max = _decimal(response.get("scale_max"), "scale_max")
        if scale_min != 1 or scale_max != 5 or not 1 <= score <= 5:
            continue
        country = response.get("country_code")
        metric_date = _business_date(response.get("submitted_at"), country, "submitted_at")
        aggregate = totals[(metric_date, country, "customer_satisfaction_csat", "XXX")]
        aggregate["numerator"] += score
        aggregate["denominator"] += 1

    rows: list[dict[str, Any]] = []
    for (metric_date, country, metric_code, currency_code), aggregate in sorted(totals.items()):
        numerator = aggregate["numerator"]
        denominator = aggregate["denominator"]
        if metric_code in {"on_time_delivery_rate", "customer_satisfaction_csat"}:
            if denominator == 0:
                continue
            metric_value = (
                numerator * Decimal(100) / denominator
                if metric_code == "on_time_delivery_rate"
                else numerator / denominator
            )
            output_denominator: Decimal | None = denominator
        else:
            metric_value = numerator
            output_denominator = None
        unit = currency_code if metric_code == "operating_cost_eur" else METRIC_UNITS[metric_code]
        rows.append(
            {
                "metric_date": metric_date,
                "country_code": country,
                "metric_code": metric_code,
                "currency_code": currency_code,
                "metric_value": metric_value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
                "numerator": numerator.quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
                "denominator": (
                    output_denominator.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)
                    if output_denominator is not None
                    else None
                ),
                "unit": unit,
            }
        )
    return rows
