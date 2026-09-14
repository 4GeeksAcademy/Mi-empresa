import { getToken } from "@/lib/auth";

export type Warehouse = "los_angeles" | "zaragoza";

export interface Product {
  id: number;
  name: string;
  sku: string;
  warehouse: Warehouse;
  current_stock: number;
}

export interface InventoryOrder {
  id: number;
  product_id: number;
  product_name: string;
  product_sku: string;
  quantity: number;
  direction: "inbound" | "outbound";
  created_at: string;
  user_uuid: string;
}

export class InventoryApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "InventoryApiError";
  }
}

const API_BASE_URL = (process.env.NEXT_PUBLIC_INVENTORY_API_URL ?? "/api/inventory").replace(/\/$/, "");
const API_PATH_PREFIX = API_BASE_URL.endsWith("/api/inventory") ? "" : "/inventory";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  if (!token) {
    throw new InventoryApiError("Tu sesión ha caducado. Inicia sesión para continuar.", 401);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_PATH_PREFIX}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...init.headers,
      },
    });
  } catch {
    throw new InventoryApiError("No se pudo conectar con el servicio de inventario.", 0);
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail
      ? typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail)
      : null;
    throw new InventoryApiError(
      detail ?? `El servicio de inventario respondió con un error (${response.status}).`,
      response.status,
    );
  }

  return body as T;
}

export function listProducts(): Promise<Product[]> {
  return request<Product[]>("/inventory/products");
}

export function getProduct(productId: number): Promise<Product> {
  return request<Product>(`/inventory/products/${productId}`);
}

export function createInboundOrder(product_id: number, quantity: number): Promise<InventoryOrder> {
  return request<InventoryOrder>("/inventory/orders/inbound", {
    method: "POST",
    body: JSON.stringify({ product_id, quantity }),
  });
}

export function createOutboundOrder(product_id: number, quantity: number): Promise<InventoryOrder> {
  return request<InventoryOrder>("/inventory/orders/outbound", {
    method: "POST",
    body: JSON.stringify({ product_id, quantity }),
  });
}

export function listOrders(): Promise<InventoryOrder[]> {
  return request<InventoryOrder[]>("/inventory/orders");
}