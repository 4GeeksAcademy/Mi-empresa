#!/usr/bin/env python3
"""
Script de seed de incidencias historicas.

Lee el CSV del proyecto anterior (incidents-COMPANY.csv) y carga las filas
validas en la base de datos como incidencias de tipo "customer".

Transformaciones aplicadas:
- CSV category -> modelo category (igual)
- CSV status -> modelo status (mapeo: abierto->open, en_progreso->in_progress, cerrado->resolved, descartado->discarded)
- CSV incident_id -> usado para idempotencia
- origin = "customer" (fijo para todos los registros historicos)
- branch = "central" (valor por defecto, el CSV historico no tiene sede)
- title = generado a partir de categoria e incident_id
- description = generado a partir de los datos del CSV
- created_at = fecha actual (el CSV no tiene columna de fecha)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

# Asegurar que el repo root esta en sys.path para poder importar packages/shared
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Asegurar que services/api esta en sys.path para importar los modulos de incidents
_SERVICES_API_PATH = _REPO_ROOT / "services" / "api"
if str(_SERVICES_API_PATH) not in sys.path:
    sys.path.insert(0, str(_SERVICES_API_PATH))

from packages.shared.validators import (
    normalize,
    normalize_key,
    validate_record,
)

from incidents.models import (
    STATUS_TRANSITION_MAP,
    IncidentCreate,
)

from incidents.repository import IncidentRepository


CSV_PATH = _REPO_ROOT / "scripts" / "incidents-COMPANY.csv"

CATEGORY_TITLE_PREFIX = {
    "logistica": "Incidencia logistica",
    "tracking": "Problema de tracking",
    "devolucion": "Incidencia de devolucion",
    "facturacion": "Incidencia de facturacion",
    "soporte": "Consulta de soporte",
}


def csv_incident_id_to_title(incident_id: str, category: str) -> str:
    """Genera un titulo descriptivo a partir del ID y categoria del CSV."""
    prefix = CATEGORY_TITLE_PREFIX.get(category, "Incidencia")
    return f"{prefix} - {incident_id}"


def csv_incident_id_to_description(incident_id: str, category: str, csv_status: str) -> str:
    """Genera una descripcion a partir de los datos del CSV."""
    status_label = {
        "abierto": "reportada",
        "en_progreso": "en curso",
        "cerrado": "resuelta",
        "descartado": "descartada",
    }.get(csv_status, csv_status)
    return (
        f"Incidencia historica {incident_id} de categoria '{category}' "
        f"en estado '{status_label}', registrada como incidencia de cliente "
        f"durante el proceso de migracion de datos."
    )


def run_seed() -> int:
    csv_path = CSV_PATH
    if not csv_path.exists():
        print(f"ERROR: No se encuentra el archivo CSV: {csv_path}")
        return 1

    repo = IncidentRepository()
    csv_text = csv_path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(csv_text.splitlines())

    if reader.fieldnames is None:
        print("ERROR: No se pudo leer la cabecera del CSV.")
        return 1

    # Normalizar fieldnames
    fieldnames = [normalize_key(name) for name in reader.fieldnames]

    total_rows = 0
    inserted = 0
    skipped_existing = 0
    invalid_rows = 0
    invalid_details: list[str] = []

    for row in reader:
        total_rows += 1
        normalized_row = {
            normalize_key(key): normalize(value)
            for key, value in row.items()
            if key is not None
        }

        csv_incident_id = normalized_row.get("incident_id", "")

        # Validar registro usando la logica compartida
        errors = validate_record(normalized_row)
        if errors:
            invalid_rows += 1
            reason = "; ".join(errors)
            invalid_details.append(f"  {csv_incident_id}: {reason}")
            continue

        # Comprobar idempotencia
        # Usamos incident_id como identificador unico del CSV
        idempotency_key = f"csv_{csv_incident_id}"
        if repo.find_by_csv_id(idempotency_key):
            skipped_existing += 1
            continue

        category = normalized_row.get("category", "").lower()
        csv_status = normalized_row.get("status", "").lower()

        # Transformar estado CSV -> modelo
        new_status = STATUS_TRANSITION_MAP.get(csv_status, "open")

        # Generar titulo y descripcion
        title = csv_incident_id_to_title(csv_incident_id, category)
        description = csv_incident_id_to_description(csv_incident_id, category, csv_status)

        # Construir la incidencia
        try:
            incident_input = IncidentCreate(
                title=title,
                description=description,
                category=category,
                status=new_status,
                origin="customer",
                branch="central",
            )
            repo.create(incident_input)
            repo.mark_csv_id_inserted(idempotency_key)
            inserted += 1
        except Exception as exc:
            invalid_rows += 1
            invalid_details.append(f"  {csv_incident_id}: Error al insertar: {exc}")

    # Reporte final
    print("=" * 60)
    print("RESUMEN DE CARGA DE INCIDENCIAS HISTORICAS")
    print("=" * 60)
    print(f"Total registros en CSV:      {total_rows}")
    print(f"Insertados:                  {inserted}")
    print(f"Omitidos (ya existentes):    {skipped_existing}")
    print(f"Invalidos:                   {invalid_rows}")

    if invalid_details:
        print("\nRegistros invalidos:")
        for detail in invalid_details:
            print(detail)

    print(f"\nEstado final: {inserted} incidencias cargadas correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_seed())