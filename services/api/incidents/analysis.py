from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from typing import Any

REQUIRED_FIELDS = ("incident_id", "category", "status")
CATEGORY_FIELD = "category"
STATUS_FIELD = "status"
SATISFACTION_FIELD = "satisfaction_score"

ALLOWED_CATEGORIES = {
    "logistica",
    "tracking",
    "devolucion",
    "facturacion",
    "soporte",
}

ALLOWED_STATUSES = {
    "abierto",
    "en_progreso",
    "cerrado",
    "descartado",
}

CLOSED_STATUS = "cerrado"


class CsvFormatError(ValueError):
    pass


@dataclass
class AnalysisResult:
    total_processed: int
    total_valid: int
    total_invalid: int
    invalid_breakdown: dict[str, int]
    category_totals: dict[str, int]
    status_totals: dict[str, int]
    satisfaction_index_closed: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "total_processed": self.total_processed,
            "total_valid": self.total_valid,
            "total_invalid": self.total_invalid,
            "invalid_breakdown": self.invalid_breakdown,
            "category_totals": self.category_totals,
            "status_totals": self.status_totals,
            "satisfaction_index_closed": self.satisfaction_index_closed,
            "data_contract": {
                "required_fields": list(REQUIRED_FIELDS),
                "allowed_categories": sorted(ALLOWED_CATEGORIES),
                "allowed_statuses": sorted(ALLOWED_STATUSES),
                "satisfaction_field": SATISFACTION_FIELD,
            },
        }

    def to_metrics_rows(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = [
            ("total_processed", str(self.total_processed)),
            ("total_valid", str(self.total_valid)),
            ("total_invalid", str(self.total_invalid)),
        ]

        for reason, count in sorted(self.invalid_breakdown.items()):
            rows.append((f"invalid_{reason}", str(count)))

        for category, count in sorted(self.category_totals.items()):
            rows.append((f"category_{category}", str(count)))

        for status, count in sorted(self.status_totals.items()):
            rows.append((f"status_{status}", str(count)))

        rows.append(
            (
                "satisfaction_index_closed",
                "" if self.satisfaction_index_closed is None else f"{self.satisfaction_index_closed:.2f}",
            )
        )
        return rows


def _normalize(value: str | None) -> str:
    return (value or "").strip()


def _normalize_key(key: str | None) -> str:
    return _normalize(key).lower()


def _parse_optional_score(raw: str | None) -> float | None:
    value = _normalize(raw)
    if value == "":
        return None

    try:
        score = float(value)
    except ValueError:
        return None

    if score < 0 or score > 5:
        return None

    return score


def _validate_record(record: dict[str, str]) -> list[str]:
    errors: list[str] = []

    missing_fields = [field for field in REQUIRED_FIELDS if _normalize(record.get(field)) == ""]
    if missing_fields:
        errors.append("missing_required_field")

    category = _normalize(record.get(CATEGORY_FIELD)).lower()
    if category and category not in ALLOWED_CATEGORIES:
        errors.append("invalid_category")

    status = _normalize(record.get(STATUS_FIELD)).lower()
    if status and status not in ALLOWED_STATUSES:
        errors.append("invalid_status")

    return errors


def analyze_incidents_csv(csv_text: str) -> AnalysisResult:
    if _normalize(csv_text) == "":
        raise CsvFormatError("El fichero CSV esta vacio.")

    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise CsvFormatError("No se pudo leer la cabecera del CSV.")

    normalized_fieldnames = [_normalize_key(name) for name in reader.fieldnames]
    if any(name == "" for name in normalized_fieldnames):
        raise CsvFormatError("La cabecera del CSV contiene columnas vacias.")

    for required in REQUIRED_FIELDS:
        if required not in normalized_fieldnames:
            raise CsvFormatError(
                f"Falta la columna obligatoria '{required}' en la cabecera del CSV."
            )

    normalized_rows: list[dict[str, str]] = []
    for row in reader:
        normalized_row = {
            _normalize_key(key): _normalize(value)
            for key, value in row.items()
            if key is not None
        }

        if all(value == "" for value in normalized_row.values()):
            continue

        normalized_rows.append(normalized_row)

    total_processed = len(normalized_rows)
    invalid_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    closed_scores: list[float] = []

    for row in normalized_rows:
        errors = _validate_record(row)
        if errors:
            invalid_counter.update(errors)
            continue

        category = _normalize(row.get(CATEGORY_FIELD)).lower()
        status = _normalize(row.get(STATUS_FIELD)).lower()

        category_counter[category] += 1
        status_counter[status] += 1

        if status == CLOSED_STATUS:
            score = _parse_optional_score(row.get(SATISFACTION_FIELD))
            if score is not None:
                closed_scores.append(score)

    total_invalid = sum(invalid_counter.values())
    valid_records = total_processed - len(
        [
            row
            for row in normalized_rows
            if _validate_record(row)
        ]
    )

    satisfaction_index = None
    if closed_scores:
        satisfaction_index = sum(closed_scores) / len(closed_scores)

    return AnalysisResult(
        total_processed=total_processed,
        total_valid=valid_records,
        total_invalid=total_processed - valid_records,
        invalid_breakdown=dict(sorted(invalid_counter.items())),
        category_totals=dict(sorted(category_counter.items())),
        status_totals=dict(sorted(status_counter.items())),
        satisfaction_index_closed=satisfaction_index,
    )
