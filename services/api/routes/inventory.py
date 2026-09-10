from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, func, select

from auth import get_current_user
from database import get_db
from models import InboundOrder, OutboundOrder, Product
from schemas import (
    InboundOrderCreateInput,
    InventoryOrderResponse,
    OutboundOrderCreateInput,
    ProductCreateInput,
    ProductResponse,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _stock_by_product(db: Session) -> dict[int, int]:
    """Calcula el stock de todos los productos en dos consultas agregadas (sin N+1)."""
    inbound_totals = dict(
        db.exec(
            select(InboundOrder.product_id, func.sum(InboundOrder.quantity)).group_by(
                InboundOrder.product_id
            )
        ).all()
    )
    outbound_totals = dict(
        db.exec(
            select(OutboundOrder.product_id, func.sum(OutboundOrder.quantity)).group_by(
                OutboundOrder.product_id
            )
        ).all()
    )
    product_ids = set(inbound_totals) | set(outbound_totals)
    return {
        product_id: inbound_totals.get(product_id, 0) - outbound_totals.get(product_id, 0)
        for product_id in product_ids
    }


def _current_stock(db: Session, product_id: int) -> int:
    inbound_total = db.exec(
        select(func.sum(InboundOrder.quantity)).where(InboundOrder.product_id == product_id)
    ).one()
    outbound_total = db.exec(
        select(func.sum(OutboundOrder.quantity)).where(OutboundOrder.product_id == product_id)
    ).one()
    return (inbound_total or 0) - (outbound_total or 0)


@router.get("/products", response_model=list[ProductResponse])
def list_products(db: Session = Depends(get_db)) -> list[ProductResponse]:
    products = db.exec(select(Product)).all()
    stock_by_product = _stock_by_product(db)
    return [
        ProductResponse(
            id=product.id,
            name=product.name,
            sku=product.sku,
            warehouse=product.warehouse,
            current_stock=stock_by_product.get(product.id, 0),
        )
        for product in products
    ]


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ProductResponse:
    existing = db.exec(
        select(Product).where(
            Product.sku == payload.sku, Product.warehouse == payload.warehouse
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un producto con ese SKU en ese almacen.",
        )

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return ProductResponse(
        id=product.id,
        name=product.name,
        sku=product.sku,
        warehouse=product.warehouse,
        current_stock=0,
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductResponse:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return ProductResponse(
        id=product.id,
        name=product.name,
        sku=product.sku,
        warehouse=product.warehouse,
        current_stock=_current_stock(db, product_id),
    )


@router.post(
    "/orders/inbound",
    response_model=InventoryOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inbound_order(
    payload: InboundOrderCreateInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> InventoryOrderResponse:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    order = InboundOrder(
        product_id=payload.product_id,
        quantity=payload.quantity,
        user_uuid=str(current_user["id"]),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return InventoryOrderResponse(
        id=order.id,
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku,
        quantity=order.quantity,
        direction="inbound",
        created_at=order.created_at,
        user_uuid=order.user_uuid,
    )


@router.post(
    "/orders/outbound",
    response_model=InventoryOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_outbound_order(
    payload: OutboundOrderCreateInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> InventoryOrderResponse:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    stock = _current_stock(db, payload.product_id)
    if payload.quantity > stock:
        raise HTTPException(
            status_code=400,
            detail=f"Stock insuficiente: disponible {stock}, solicitado {payload.quantity}.",
        )

    order = OutboundOrder(
        product_id=payload.product_id,
        quantity=payload.quantity,
        user_uuid=str(current_user["id"]),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return InventoryOrderResponse(
        id=order.id,
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku,
        quantity=order.quantity,
        direction="outbound",
        created_at=order.created_at,
        user_uuid=order.user_uuid,
    )


@router.get("/orders", response_model=list[InventoryOrderResponse])
def list_orders(db: Session = Depends(get_db)) -> list[InventoryOrderResponse]:
    inbound_rows = db.exec(select(InboundOrder, Product).join(Product)).all()
    outbound_rows = db.exec(select(OutboundOrder, Product).join(Product)).all()

    orders = [
        InventoryOrderResponse(
            id=order.id,
            product_id=product.id,
            product_name=product.name,
            product_sku=product.sku,
            quantity=order.quantity,
            direction="inbound",
            created_at=order.created_at,
            user_uuid=order.user_uuid,
        )
        for order, product in inbound_rows
    ] + [
        InventoryOrderResponse(
            id=order.id,
            product_id=product.id,
            product_name=product.name,
            product_sku=product.sku,
            quantity=order.quantity,
            direction="outbound",
            created_at=order.created_at,
            user_uuid=order.user_uuid,
        )
        for order, product in outbound_rows
    ]
    orders.sort(key=lambda item: item.created_at)
    return orders
