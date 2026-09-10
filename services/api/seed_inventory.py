from __future__ import annotations

from sqlmodel import Session, select

from database import get_engine, init_inventory_db
from models import InboundOrder, OutboundOrder, Product, Warehouse

SEED_PRODUCTS = [
    {"name": "Caja de embalaje reforzada", "sku": "PKG-001", "warehouse": Warehouse.LOS_ANGELES},
    {"name": "Etiqueta termica de envio", "sku": "PKG-002", "warehouse": Warehouse.ZARAGOZA},
    {"name": "Paleta de almacenaje estandar", "sku": "WH-010", "warehouse": Warehouse.LOS_ANGELES},
]

# (sku, entradas, salidas) -> neto coherente por producto
SEED_MOVEMENTS = {
    "PKG-001": (50, 20),
    "PKG-002": (80, 35),
    "WH-010": (15, 5),
}

SEED_USER_UUID = "seed-user"


def run_inventory_seed() -> int:
    init_inventory_db()
    inserted = 0

    with Session(get_engine()) as session:
        for product_data in SEED_PRODUCTS:
            existing = session.exec(
                select(Product).where(
                    Product.sku == product_data["sku"],
                    Product.warehouse == product_data["warehouse"],
                )
            ).first()
            if existing is not None:
                continue

            product = Product(**product_data)
            session.add(product)
            session.commit()
            session.refresh(product)
            inserted += 1

            inbound_qty, outbound_qty = SEED_MOVEMENTS[product.sku]
            session.add(
                InboundOrder(
                    product_id=product.id,
                    quantity=inbound_qty,
                    user_uuid=SEED_USER_UUID,
                )
            )
            session.add(
                OutboundOrder(
                    product_id=product.id,
                    quantity=outbound_qty,
                    user_uuid=SEED_USER_UUID,
                )
            )
            session.commit()

    print(f"Seed de inventario completado. Productos insertados: {inserted}")
    return inserted


if __name__ == "__main__":
    run_inventory_seed()
