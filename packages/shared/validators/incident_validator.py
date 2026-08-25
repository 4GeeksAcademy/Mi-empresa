from __future__ import annotations

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


def normalize(value: str | None) -> str:
    """Normaliza un valor: strip de espacios y manejo de None."""
    return (value or "").strip()


def normalize_key(key: str | None) -> str:
    """Normaliza una clave de diccionario: strip + lowercase."""
    return normalize(key).lower()


def parse_optional_score(raw: str | None) -> float | None:
    """Parsea un score opcional de satisfaccion (0-5)."""
    value = normalize(raw)
    if value == "":
        return None

    try:
        score = float(value)
    except ValueError:
        return None

    if score < 0 or score > 5:
        return None

    return score


def validate_record(record: dict[str, str]) -> list[str]:
    """Valida un registro del CSV y devuelve una lista de errores (vacia si es valido)."""
    errors: list[str] = []

    missing_fields = [
        field
        for field in REQUIRED_FIELDS
        if normalize(record.get(field)) == ""
    ]
    if missing_fields:
        errors.append("missing_required_field")

    category = normalize(record.get(CATEGORY_FIELD)).lower()
    if category and category not in ALLOWED_CATEGORIES:
        errors.append("invalid_category")

    status = normalize(record.get(STATUS_FIELD)).lower()
    if status and status not in ALLOWED_STATUSES:
        errors.append("invalid_status")

    return errors