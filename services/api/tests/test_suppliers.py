import os
from pathlib import Path

from fastapi.testclient import TestClient

from auth import create_access_token, hash_password
from auth_db import get_user_repository, get_profile_repository
from auth_models import UserPersistence, utc_now_iso
from database import get_suppliers_repository
from main import app
from seed import run_seed

client = TestClient(app)

TEST_ADMIN_EMAIL = "admin@trackflow.com"
TEST_ADMIN_PASSWORD = "admin123"


def _ensure_admin_user() -> str:
    """Crea un usuario admin de prueba y devuelve un token JWT."""
    repo = get_user_repository()
    existing = repo.get_by_email(TEST_ADMIN_EMAIL)
    if existing is None:
        user_persistence = UserPersistence(
            email=TEST_ADMIN_EMAIL,
            hashed_password=hash_password(TEST_ADMIN_PASSWORD),
            role="admin",
            is_active=True,
            created_at=utc_now_iso(),
        )
        created = repo.create(user_persistence)
        user_id = created.id
    else:
        user_id = existing.id

    token = create_access_token(data={"sub": str(user_id)})
    return token


def _auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {_ensure_admin_user()}"}


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

    tmp_auth_db = Path("/tmp/trackflow-auth-test.json")
    if tmp_auth_db.exists():
        tmp_auth_db.unlink()
    os.environ["TRACKFLOW_AUTH_DB_PATH"] = str(tmp_auth_db)

    get_suppliers_repository.cache_clear()
    get_user_repository.cache_clear()


def teardown_function() -> None:
    get_suppliers_repository.cache_clear()
    get_user_repository.cache_clear()
    os.environ.pop("TRACKFLOW_SUPPLIERS_DB_PATH", None)
    os.environ.pop("TRACKFLOW_AUTH_DB_PATH", None)


def test_create_and_get_supplier() -> None:
    headers = _auth_header()
    created = client.post("/suppliers", json=_seeded_supplier_payload(), headers=headers)
    assert created.status_code == 201

    data = created.json()
    supplier_id = data["id"]
    assert data["nombre"] == "Proveedor Demo"

    fetched = client.get(f"/suppliers/{supplier_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == supplier_id


def test_invalid_payload_returns_422() -> None:
    headers = _auth_header()
    invalid = client.post(
        "/suppliers",
        json={
            "nombre": "   ",
            "pais": "US",
            "categorias_producto": ["transporte"],
            "tarifa_por_kg": 0,
            "status": "activo",
        },
        headers=headers,
    )
    assert invalid.status_code == 422


def test_list_filters_by_country_and_category() -> None:
    headers = _auth_header()
    client.post(
        "/suppliers",
        json={
            "nombre": "Proveedor ES",
            "pais": "ES",
            "categorias_producto": ["embalaje"],
            "tarifa_por_kg": 3.2,
            "status": "activo",
        },
        headers=headers,
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
        headers=headers,
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
    headers = _auth_header()
    created = client.post("/suppliers", json=_seeded_supplier_payload(), headers=headers)
    supplier_id = created.json()["id"]

    rate_updated = client.patch(f"/suppliers/{supplier_id}/rate", json={"tarifa_por_kg": 9.5}, headers=headers)
    assert rate_updated.status_code == 200
    assert rate_updated.json()["tarifa_por_kg"] == 9.5

    status_updated = client.patch(f"/suppliers/{supplier_id}/status", json={"status": "suspendido"}, headers=headers)
    assert status_updated.status_code == 200
    assert status_updated.json()["status"] == "suspendido"

    deleted = client.delete(f"/suppliers/{supplier_id}", headers=headers)
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
    headers = _auth_header()
    resp = client.delete("/suppliers/99999", headers=headers)
    assert resp.status_code == 404


def test_create_rejects_extra_fields() -> None:
    """POST /suppliers must reject payloads with unknown fields like updated_at."""
    headers = _auth_header()
    payload = _seeded_supplier_payload()
    payload["updated_at"] = "2026-01-01T00:00:00+00:00"
    resp = client.post("/suppliers", json=payload, headers=headers)
    assert resp.status_code == 422


def test_list_filters_by_country_and_category_aliases() -> None:
    """GET /suppliers must accept both country/category and pais/categoria params."""
    headers = _auth_header()
    client.post(
        "/suppliers",
        json={
            "nombre": "Aliased ES",
            "pais": "ES",
            "categorias_producto": ["almacenaje"],
            "tarifa_por_kg": 2.5,
            "status": "activo",
        },
        headers=headers,
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
        headers=headers,
    )

    by_country = client.get("/suppliers", params={"country": "ES"})
    assert by_country.status_code == 200
    assert len(by_country.json()) == 1
    assert by_country.json()[0]["pais"] == "ES"

    by_category = client.get("/suppliers", params={"category": "almacenaje"})
    assert by_category.status_code == 200
    assert len(by_category.json()) == 1
    assert by_category.json()[0]["nombre"] == "Aliased ES"
