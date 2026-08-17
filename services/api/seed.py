from __future__ import annotations

from database import get_seed_suppliers, get_suppliers_repository


def run_seed() -> int:
    repo = get_suppliers_repository()
    inserted = 0

    for supplier in get_seed_suppliers():
        existing = repo.find_by_name_and_country(supplier.nombre, supplier.pais)
        if existing is not None:
            continue
        repo.create(supplier)
        inserted += 1

    print(f"Seed completado. Registros insertados: {inserted}")
    return inserted


if __name__ == "__main__":
    run_seed()
