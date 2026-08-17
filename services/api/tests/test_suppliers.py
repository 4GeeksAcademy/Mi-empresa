import os
from pathlib import Path

from fastapi.testclient import TestClient

from database import get_suppliers_repository
from main import app
from seed import run_seed

client = TestClient(app)


def _seeded_supplier_payload() -> dict[str, object]:
    return {
        "nombre": "Proveedor Demo",
        "pais": "US",
        "categorias_producto": ["transporte", "devoluciones"],
        "tarifa_por_kg": 4.2,
        "status": "activo",
    }


def setup_function() -> None:
    tmp_db = Path("/tmp/trackflow-suppliers-test.json")
    if tmp_db.exists():
        tmp_db.unlink()
    os.environ["TRACKFLOW_SUPPLIERS_DB_PATH"] = str(tmp_db)
    get_suppliers_repository.cache_clear()


def teardown_function() -> None:
    get_suppliers_repository.cache_clear()
    os.environ.pop("TRACKFLOW_SUPPLIERS_DB_PATH", None)


def test_create_and_get_supplier() -> None:
    created = client.post("/suppliers", json=_seeded_supplier_payload())
    assert created.status_code == 201

    data = created.json()
    supplier_id = data["id"]
    assert data["nombre"] == "Proveedor Demo"

    fetched = client.get(f"/suppliers/{supplier_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == supplier_id


def test_invalid_payload_returns_422() -> None:
    invalid = client.post(
        "/suppliers",
        json={
            "nombre": "   ",
            "pais": "US",
            "categorias_producto": ["transporte"],
            "tarifa_por_kg": 0,
            "status": "activo",
        },
    )
    assert invalid.status_code == 422


def test_list_filters_by_country_and_category() -> None:
    client.post(
        "/suppliers",
        json={
            "nombre": "Proveedor ES",
            "pais": "ES",
            "categorias_producto": ["embalaje"],
            "tarifa_por_kg": 3.2,
            "status": "activo",
        },
    )
    client.post(
        "/suppliers",
        json={
            "nombre": "Proveedor US",
            "pais": "US",
            "categorias_producto": ["transporte"],
            "tarifa_por_kg": 7.1,
            "status": "activo",
        },
    )

    by_country = client.get("/suppliers", params={"pais": "ES"})
    assert by_country.status_code == 200
    assert len(by_country.json()) == 1
    assert by_country.json()[0]["pais"] == "ES"

    by_category = client.get("/suppliers", params={"categoria": "transporte"})
    assert by_category.status_code == 200
    assert len(by_category.json()) == 1
    assert by_category.json()[0]["nombre"] == "Proveedor US"


def test_update_rate_and_status_and_delete() -> None:
    created = client.post("/suppliers", json=_seeded_supplier_payload())
    supplier_id = created.json()["id"]

    rate_updated = client.patch(f"/suppliers/{supplier_id}/rate", json={"tarifa_por_kg": 9.5})
    assert rate_updated.status_code == 200
    assert rate_updated.json()["tarifa_por_kg"] == 9.5

    status_updated = client.patch(f"/suppliers/{supplier_id}/status", json={"status": "suspendido"})
    assert status_updated.status_code == 200
    assert status_updated.json()["status"] == "suspendido"

    deleted = client.delete(f"/suppliers/{supplier_id}")
    assert deleted.status_code == 200

    missing = client.get(f"/suppliers/{supplier_id}")
    assert missing.status_code == 404


def test_seed_is_idempotent() -> None:
    inserted_first = run_seed()
    inserted_second = run_seed()

    assert inserted_first > 0
    assert inserted_second == 0


def test_delete_nonexistent_returns_404() -> None:
    """DELETE /suppliers/{id} must return 404 when id does not exist."""
    resp = client.delete("/suppliers/99999")
    assert resp.status_code == 404


def test_create_rejects_extra_fields() -> None:
    """POST /suppliers must reject payloads with unknown fields like updated_at."""
    payload = _seeded_supplier_payload()
    payload["updated_at"] = "2026-01-01T00:00:00+00:00"
    resp = client.post("/suppliers", json=payload)
    assert resp.status_code == 422


def test_list_filters_by_country_and_category_aliases() -> None:
    """GET /suppliers must accept both country/category and pais/categoria params."""
    client.post(
        "/suppliers",
        json={
            "nombre": "Aliased ES",
            "pais": "ES",
            "categorias_producto": ["almacenaje"],
            "tarifa_por_kg": 2.5,
            "status": "activo",
        },
    )
    client.post(
        "/suppliers",
        json={
            "nombre": "Aliased US",
            "pais": "US",
            "categorias_producto": ["transporte"],
            "tarifa_por_kg": 6.0,
            "status": "activo",
        },
    )

    by_country = client.get("/suppliers", params={"country": "ES"})
    assert by_country.status_code == 200
    assert len(by_country.json()) == 1
    assert by_country.json()[0]["pais"] == "ES"

    by_category = client.get("/suppliers", params={"category": "almacenaje"})
    assert by_category.status_code == 200
    assert len(by_category.json()) == 1
    assert by_category.json()[0]["nombre"] == "Aliased ES"
