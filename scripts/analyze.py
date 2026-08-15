#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_API_PATH = REPO_ROOT / "services" / "api"
if str(SERVICE_API_PATH) not in sys.path:
    sys.path.insert(0, str(SERVICE_API_PATH))

from incidents import CsvFormatError, analyze_incidents_csv  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analiza un CSV de incidencias y muestra metricas operativas.",
    )
    parser.add_argument(
        "csv_path",
        type=Path,
        help="Ruta al fichero CSV (ej: incidents-COMPANY.csv)",
    )
    parser.add_argument(
        "--expected",
        type=Path,
        default=None,
        help="Ruta opcional a JSON con metricas esperadas para verificacion.",
    )
    return parser


def print_summary(result: dict[str, object]) -> None:
    print("=" * 64)
    print("Resumen del Analizador de Incidencias")
    print("=" * 64)
    print(f"Total procesados: {result['total_processed']}")
    print(f"Total validos:    {result['total_valid']}")
    print(f"Total invalidos:  {result['total_invalid']}")

    print("\nInvalidos por tipo:")
    invalid_breakdown = result["invalid_breakdown"]
    if invalid_breakdown:
        for reason, count in invalid_breakdown.items():
            print(f"- {reason}: {count}")
    else:
        print("- Sin registros invalidos")

    print("\nTotales por categoria:")
    category_totals = result["category_totals"]
    if category_totals:
        for category, count in category_totals.items():
            print(f"- {category}: {count}")
    else:
        print("- Sin datos")

    print("\nTotales por estado:")
    status_totals = result["status_totals"]
    if status_totals:
        for status, count in status_totals.items():
            print(f"- {status}: {count}")
    else:
        print("- Sin datos")

    score = result["satisfaction_index_closed"]
    if score is None:
        print("\nIndice de satisfaccion (cerrado con puntuacion): N/A")
    else:
        print(f"\nIndice de satisfaccion (cerrado con puntuacion): {score:.2f}")


def verify_expected(result: dict[str, object], expected_path: Path) -> bool:
    expected_data = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_summary = expected_data.get("summary", expected_data)

    keys_to_check = [
        "total_processed",
        "total_valid",
        "total_invalid",
        "invalid_breakdown",
        "category_totals",
        "status_totals",
        "satisfaction_index_closed",
    ]

    mismatches: list[str] = []
    for key in keys_to_check:
        expected_value = expected_summary.get(key)
        current_value = result.get(key)
        if expected_value != current_value:
            mismatches.append(
                f"{key}: esperado={expected_value!r}, actual={current_value!r}"
            )

    if mismatches:
        print("\n[VERIFICACION] ERROR: los resultados NO coinciden con los esperados.")
        for mismatch in mismatches:
            print(f"- {mismatch}")
        return False

    print("\n[VERIFICACION] OK: resultados alineados con valores esperados del contexto.")
    return True


def export_results(result: dict[str, object], output_path: Path) -> None:
    rows: list[tuple[str, str]] = [
        ("metric", "value"),
        ("total_processed", str(result["total_processed"])),
        ("total_valid", str(result["total_valid"])),
        ("total_invalid", str(result["total_invalid"])),
    ]

    for reason, count in result["invalid_breakdown"].items():
        rows.append((f"invalid_{reason}", str(count)))

    for category, count in result["category_totals"].items():
        rows.append((f"category_{category}", str(count)))

    for status, count in result["status_totals"].items():
        rows.append((f"status_{status}", str(count)))

    score = result["satisfaction_index_closed"]
    rows.append(("satisfaction_index_closed", "" if score is None else f"{score:.2f}"))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    output_path.write_text(buffer.getvalue(), encoding="utf-8")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    csv_path: Path = args.csv_path
    if not csv_path.exists():
        print(f"ERROR: el archivo no existe: {csv_path}")
        return 1

    csv_text = csv_path.read_text(encoding="utf-8-sig")

    try:
        analysis = analyze_incidents_csv(csv_text)
    except CsvFormatError as exc:
        print(f"ERROR: {exc}")
        return 1

    summary = analysis.to_json()
    print_summary(summary)

    expected_path: Path | None = args.expected
    if expected_path is None:
        candidate = csv_path.with_suffix(".expected.json")
        if candidate.exists():
            expected_path = candidate

    verification_ok = True
    if expected_path is not None:
        try:
            verification_ok = verify_expected(summary, expected_path)
        except Exception as exc:  # noqa: BLE001
            print(f"\n[VERIFICACION] ERROR leyendo expected file: {exc}")
            verification_ok = False
    else:
        print("\n[VERIFICACION] Sin archivo expected.json: verificacion automatica omitida.")

    answer = input("\n¿Deseas exportar los resultados a CSV? [s/n]: ").strip().lower()
    if answer == "s":
        export_path = Path("results.csv")
        export_results(summary, export_path)
        print(f"Archivo generado: {export_path.resolve()}")

    return 0 if verification_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
