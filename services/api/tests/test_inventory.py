from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from auth import create_access_token, hash_password
from auth_db import get_user_repository
from auth_models import UserPersistence, utc_now_iso
from database import get_db
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


def test_inventory_products_and_stock_movements() -> None:
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
            headers = _auth_header()
            created = client.post(
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

            inbound = client.post(
                "/inventory/orders/inbound",
                json={"product_id": product["id"], "quantity": 10},
                headers=headers,
            )
            assert inbound.status_code == 201
            assert inbound.json()["direction"] == "inbound"

            outbound = client.post(
                "/inventory/orders/outbound",
                json={"product_id": product["id"], "quantity": 4},
                headers=headers,
            )
            assert outbound.status_code == 201
            assert outbound.json()["direction"] == "outbound"

            detail = client.get(f"/inventory/products/{product['id']}")
            assert detail.status_code == 200
            assert detail.json()["current_stock"] == 6
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_inventory_rejects_duplicate_partition_and_insufficient_stock() -> None:
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
            headers = _auth_header()
            payload = {
                "name": "SKU compartido",
                "sku": "TEST-002",
                "warehouse": "los_angeles",
            }
            first = client.post("/inventory/products", json=payload, headers=headers)
            assert first.status_code == 201

            duplicate = client.post("/inventory/products", json=payload, headers=headers)
            assert duplicate.status_code == 400

            other_warehouse = client.post(
                "/inventory/products",
                json={**payload, "warehouse": "zaragoza"},
                headers=headers,
            )
            assert other_warehouse.status_code == 201

            inbound = client.post(
                "/inventory/orders/inbound",
                json={"product_id": first.json()["id"], "quantity": 2},
                headers=headers,
            )
            assert inbound.status_code == 201

            rejected = client.post(
                "/inventory/orders/outbound",
                json={"product_id": first.json()["id"], "quantity": 3},
                headers=headers,
            )
            assert rejected.status_code == 400

            orders = client.get("/inventory/orders")
            assert orders.status_code == 200
            assert len(orders.json()) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_inventory_requires_authentication_to_create_product() -> None:
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
            response = client.post(
                "/inventory/products",
                json={
                    "name": "Sin autenticar",
                    "sku": "TEST-003",
                    "warehouse": "zaragoza",
                },
            )
            assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)