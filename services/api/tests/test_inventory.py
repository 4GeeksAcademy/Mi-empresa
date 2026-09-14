from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from auth import create_access_token, hash_password
from auth_db import get_user_repository
from auth_models import UserPersistence, utc_now_iso
from database import get_db, get_engine
from main import app


def _auth_header() -> dict[str, str]:
    email = "inventory-test@trackflow.com"
    repository = get_user_repository()
    user = repository.get_by_email(email)
    if user is None:
        user = repository.create(
            UserPersistence(
                email=email,
                hashed_password=hash_password("inventory-test-password"),
                role="admin",
                is_active=True,
                created_at=utc_now_iso(),
            )
        )

    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def inventory_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'lifespan.db'}")
    get_engine.cache_clear()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        get_engine.cache_clear()


def test_inventory_products_and_stock_movements(inventory_client: TestClient) -> None:
    headers = _auth_header()
    created = inventory_client.post(
        "/inventory/products",
        json={
            "name": "Caja de prueba",
            "sku": "TEST-001",
            "warehouse": "los_angeles",
        },
        headers=headers,
    )
    assert created.status_code == 201
    product = created.json()
    assert product["current_stock"] == 0

    inbound = inventory_client.post(
        "/inventory/orders/inbound",
        json={"product_id": product["id"], "quantity": 10},
        headers=headers,
    )
    assert inbound.status_code == 201
    assert inbound.json()["direction"] == "inbound"

    outbound = inventory_client.post(
        "/inventory/orders/outbound",
        json={"product_id": product["id"], "quantity": 4},
        headers=headers,
    )
    assert outbound.status_code == 201
    assert outbound.json()["direction"] == "outbound"

    detail = inventory_client.get(f"/inventory/products/{product['id']}")
    assert detail.status_code == 200
    assert detail.json()["current_stock"] == 6


def test_inventory_lists_products_and_returns_not_found_for_unknown_product(
    inventory_client: TestClient,
) -> None:
    headers = _auth_header()
    created = inventory_client.post(
        "/inventory/products",
        json={"name": "Producto listado", "sku": "TEST-LIST", "warehouse": "zaragoza"},
        headers=headers,
    )
    assert created.status_code == 201
    product = created.json()

    products = inventory_client.get("/inventory/products")
    assert products.status_code == 200
    assert products.json() == [product]

    missing = inventory_client.get("/inventory/products/999999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Producto no encontrado."


def test_inventory_rejects_duplicate_partition_and_insufficient_stock(
    inventory_client: TestClient,
) -> None:
    headers = _auth_header()
    payload = {
        "name": "SKU compartido",
        "sku": "TEST-002",
        "warehouse": "los_angeles",
    }
    first = inventory_client.post("/inventory/products", json=payload, headers=headers)
    assert first.status_code == 201

    duplicate = inventory_client.post("/inventory/products", json=payload, headers=headers)
    assert duplicate.status_code == 400

    other_warehouse = inventory_client.post(
        "/inventory/products",
        json={**payload, "warehouse": "zaragoza"},
        headers=headers,
    )
    assert other_warehouse.status_code == 201

    inbound = inventory_client.post(
        "/inventory/orders/inbound",
        json={"product_id": first.json()["id"], "quantity": 2},
        headers=headers,
    )
    assert inbound.status_code == 201

    rejected = inventory_client.post(
        "/inventory/orders/outbound",
        json={"product_id": first.json()["id"], "quantity": 3},
        headers=headers,
    )
    assert rejected.status_code == 400

    orders = inventory_client.get("/inventory/orders")
    assert orders.status_code == 200
    assert len(orders.json()) == 1


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"sku": "TEST-INVALID", "warehouse": "los_angeles"}, 422),
        ({"name": "Producto", "sku": "TEST-INVALID", "warehouse": "otro"}, 422),
        (
            {
                "name": "Producto",
                "sku": "TEST-INVALID",
                "warehouse": "los_angeles",
                "unexpected": True,
            },
            422,
        ),
    ],
)
def test_inventory_rejects_invalid_product_payload(
    inventory_client: TestClient,
    payload: dict[str, object],
    expected_status: int,
) -> None:
    response = inventory_client.post(
        "/inventory/products", json=payload, headers=_auth_header()
    )
    assert response.status_code == expected_status


def test_inventory_rejects_invalid_quantities(inventory_client: TestClient) -> None:
    headers = _auth_header()
    product = inventory_client.post(
        "/inventory/products",
        json={"name": "Producto cantidades", "sku": "TEST-QTY", "warehouse": "los_angeles"},
        headers=headers,
    ).json()

    for direction in ("inbound", "outbound"):
        response = inventory_client.post(
            f"/inventory/orders/{direction}",
            json={"product_id": product["id"], "quantity": 0},
            headers=headers,
        )
        assert response.status_code == 422


def test_inventory_rejects_movements_for_unknown_product(inventory_client: TestClient) -> None:
    headers = _auth_header()
    for direction in ("inbound", "outbound"):
        response = inventory_client.post(
            f"/inventory/orders/{direction}",
            json={"product_id": 999999, "quantity": 1},
            headers=headers,
        )
        assert response.status_code == 404


def test_inventory_allows_exact_stock_outbound_and_lists_orders_in_creation_order(
    inventory_client: TestClient,
) -> None:
    headers = _auth_header()
    product = inventory_client.post(
        "/inventory/products",
        json={"name": "Producto salida total", "sku": "TEST-EXACT", "warehouse": "zaragoza"},
        headers=headers,
    ).json()

    inbound = inventory_client.post(
        "/inventory/orders/inbound",
        json={"product_id": product["id"], "quantity": 5},
        headers=headers,
    )
    outbound = inventory_client.post(
        "/inventory/orders/outbound",
        json={"product_id": product["id"], "quantity": 5},
        headers=headers,
    )
    assert inbound.status_code == 201
    assert outbound.status_code == 201
    assert inventory_client.get(f"/inventory/products/{product['id']}").json()["current_stock"] == 0

    orders = inventory_client.get("/inventory/orders")
    assert orders.status_code == 200
    order_rows = orders.json()
    assert [row["direction"] for row in order_rows] == ["inbound", "outbound"]
    assert [row["created_at"] for row in order_rows] == sorted(
        row["created_at"] for row in order_rows
    )
    assert {row["product_sku"] for row in order_rows} == {"TEST-EXACT"}


@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_inventory_requires_authentication_for_stock_movements(
    inventory_client: TestClient,
    direction: str,
) -> None:
    response = inventory_client.post(
        f"/inventory/orders/{direction}",
        json={"product_id": 1, "quantity": 1},
    )
    assert response.status_code == 401


def test_inventory_requires_authentication_to_create_product(
    inventory_client: TestClient,
) -> None:
    response = inventory_client.post(
        "/inventory/products",
        json={
            "name": "Sin autenticar",
            "sku": "TEST-003",
            "warehouse": "zaragoza",
        },
    )
    assert response.status_code == 401