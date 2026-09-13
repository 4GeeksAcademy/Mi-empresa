"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  createInboundOrder,
  createOutboundOrder,
  getProduct,
  InventoryApiError,
  listOrders,
  listProducts,
  type InventoryOrder,
  type Product,
  type Warehouse,
} from "@/lib/inventory";

const LOW_STOCK_THRESHOLD = 10;

const warehouseLabels: Record<Warehouse, string> = {
  los_angeles: "Los Ángeles",
  zaragoza: "Zaragoza",
};

function displayError(error: unknown): string {
  return error instanceof Error ? error.message : "Ha ocurrido un error inesperado.";
}

function useProducts() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void listProducts()
      .then((data) => {
        if (!cancelled) setProducts(data);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        if (reason instanceof InventoryApiError && reason.status === 401) {
          router.replace("/login");
          return;
        }
        setError(displayError(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return { products, setProducts, loading, error };
}

function InventoryHeader({ title, description }: { title: string; description: string }) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-teal-700">Operaciones de almacén</p>
        <h1 className="mt-2 text-3xl font-extrabold text-slate-900">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">{description}</p>
      </div>
      <nav className="flex flex-wrap gap-2 text-sm font-semibold">
        <Link href="/backoffice/inventory/products" className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-700 hover:border-teal-500 hover:text-teal-700">
          Productos
        </Link>
        <Link href="/backoffice/inventory/orders/inbound" className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-700 hover:border-teal-500 hover:text-teal-700">
          Entrada
        </Link>
        <Link href="/backoffice/inventory/orders/outbound" className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-700 hover:border-teal-500 hover:text-teal-700">
          Salida
        </Link>
        <Link href="/backoffice/inventory/orders" className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-700 hover:border-teal-500 hover:text-teal-700">
          Historial
        </Link>
      </nav>
    </header>
  );
}

function PageFrame({ children }: { children: React.ReactNode }) {
  return <main className="ops-bg min-h-screen px-4 py-10 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl">{children}</div></main>;
}

export function InventoryProducts() {
  const { products, loading, error } = useProducts();

  return (
    <PageFrame>
      <InventoryHeader title="Inventario" description="Consulta el stock actual por producto y almacén para coordinar la operación diaria." />
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Productos disponibles</h2>
            <p className="mt-1 text-sm text-slate-500">Stock bajo significa 10 unidades o menos.</p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{products.length} productos</span>
        </div>
        {loading && <p className="py-8 text-sm text-slate-500">Cargando inventario...</p>}
        {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</p>}
        {!loading && !error && products.length === 0 && <p className="py-8 text-sm text-slate-500">No hay productos registrados.</p>}
        {!loading && !error && products.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead><tr className="border-b border-slate-200 text-slate-500"><th className="px-3 py-3 font-semibold">Producto</th><th className="px-3 py-3 font-semibold">SKU</th><th className="px-3 py-3 font-semibold">Almacén</th><th className="px-3 py-3 font-semibold">Stock actual</th><th className="px-3 py-3 font-semibold">Acciones</th></tr></thead>
              <tbody>
                {products.map((product) => {
                  const lowStock = product.current_stock <= LOW_STOCK_THRESHOLD;
                  return <tr key={product.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-3 py-4 font-semibold text-slate-900">{product.name}</td>
                    <td className="px-3 py-4 text-slate-600">{product.sku}</td>
                    <td className="px-3 py-4 text-slate-600">{warehouseLabels[product.warehouse]}</td>
                    <td className="px-3 py-4"><span className={`rounded-full px-3 py-1 text-xs font-bold ${lowStock ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>{product.current_stock} unidades{lowStock ? " · Stock bajo" : ""}</span></td>
                    <td className="px-3 py-4"><div className="flex flex-wrap gap-2"><Link href={`/backoffice/inventory/orders/inbound?product=${product.id}`} className="rounded-md bg-teal-700 px-3 py-2 text-xs font-bold text-white hover:bg-teal-800">Orden de entrada</Link><Link href={`/backoffice/inventory/orders/outbound?product=${product.id}`} className="rounded-md border border-teal-700 px-3 py-2 text-xs font-bold text-teal-700 hover:bg-teal-50">Orden de salida</Link></div></td>
                  </tr>;
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </PageFrame>
  );
}

export function InventoryOrderForm({ direction }: { direction: "inbound" | "outbound" }) {
  const router = useRouter();
  const { products, loading, error } = useProducts();
  const [selectedProductId, setSelectedProductId] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("product") ?? "";
  });
  const [quantity, setQuantity] = useState("");
  const [refreshedProduct, setRefreshedProduct] = useState<Product | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");
  const [quantityError, setQuantityError] = useState("");

  useEffect(() => {
    if (!selectedProductId) return;
    const product = products.find((item) => item.id === Number(selectedProductId));
    if (!product) return;
    void getProduct(product.id)
      .then(setRefreshedProduct)
      .catch((reason: unknown) => {
        if (reason instanceof InventoryApiError && reason.status === 401) {
          router.replace("/login");
          return;
        }
        setFormError(displayError(reason));
      });
  }, [products, router, selectedProductId]);

  const selectedProduct = refreshedProduct ?? products.find((item) => item.id === Number(selectedProductId)) ?? null;

  const isOutbound = direction === "outbound";
  const title = isOutbound ? "Orden de salida" : "Orden de entrada";

  async function submitOrder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setFormError("");
    setQuantityError("");
    const parsedQuantity = Number(quantity);
    if (!selectedProductId || !Number.isInteger(parsedQuantity) || parsedQuantity <= 0) {
      setFormError("Selecciona un producto e introduce una cantidad entera positiva.");
      return;
    }
    if (isOutbound && selectedProduct && parsedQuantity > selectedProduct.current_stock) {
      setFormError(`Stock insuficiente: solo hay ${selectedProduct.current_stock} unidades disponibles.`);
      return;
    }
    setSubmitting(true);
    try {
      if (isOutbound) await createOutboundOrder(Number(selectedProductId), parsedQuantity);
      else await createInboundOrder(Number(selectedProductId), parsedQuantity);
      setQuantity("");
      setMessage(`${title} registrada correctamente.`);
      const updatedProduct = await getProduct(Number(selectedProductId));
      setRefreshedProduct(updatedProduct);
    } catch (reason: unknown) {
      if (reason instanceof InventoryApiError && reason.status === 401) {
        router.replace("/login");
      } else {
        setFormError(displayError(reason));
        if (isOutbound && reason instanceof InventoryApiError && reason.status === 400) {
          setQuantityError(reason.message);
        }
      }
    } finally {
      setSubmitting(false);
    }
  }

  return <PageFrame>
    <InventoryHeader title={title} description={isOutbound ? "Registra una salida validando el stock disponible antes de enviar." : "Registra la recepción de mercancía en un almacén de TrackFlow."} />
    <section className="max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      {loading && <p className="text-sm text-slate-500">Cargando productos...</p>}
      {(error || formError) && <p className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error || formError}</p>}
      {message && <p className="mb-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">{message}</p>}
      <form className="space-y-5" onSubmit={submitOrder}>
        <label className="block text-sm font-semibold text-slate-700">Producto
          <select value={selectedProductId} onChange={(event) => { setRefreshedProduct(null); setQuantityError(""); setSelectedProductId(event.target.value); }} className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3 text-slate-900" required>
            <option value="">Selecciona un producto</option>
            {products.map((product) => <option key={product.id} value={product.id}>{product.name} · SKU {product.sku} · {warehouseLabels[product.warehouse]}</option>)}
          </select>
        </label>
        {isOutbound && selectedProduct && <p className="rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-700">Stock actual: <strong>{selectedProduct.current_stock} unidades</strong></p>}
        <label className="block text-sm font-semibold text-slate-700">Cantidad
          <input type="number" min="1" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-3 text-slate-900" required />
        </label>
        {isOutbound && selectedProduct && Number.isInteger(Number(quantity)) && Number(quantity) > selectedProduct.current_stock && <p className="-mt-3 text-sm font-semibold text-amber-700">La cantidad supera el stock actual de {selectedProduct.current_stock} unidades.</p>}
        {quantityError && <p className="-mt-3 text-sm font-semibold text-red-700" role="alert">{quantityError}</p>}
        <button type="submit" disabled={submitting || loading} className="rounded-lg bg-teal-700 px-4 py-3 text-sm font-bold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50">{submitting ? "Guardando..." : `Registrar ${isOutbound ? "salida" : "entrada"}`}</button>
      </form>
    </section>
  </PageFrame>;
}

export function InventoryOrders() {
  const router = useRouter();
  const [orders, setOrders] = useState<InventoryOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void listOrders().then(setOrders).catch((reason: unknown) => {
      if (reason instanceof InventoryApiError && reason.status === 401) router.replace("/login");
      else setError(displayError(reason));
    }).finally(() => setLoading(false));
  }, [router]);

  return <PageFrame>
    <InventoryHeader title="Historial de órdenes" description="Consulta las entradas y salidas registradas por el equipo de operaciones." />
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      {loading && <p className="py-8 text-sm text-slate-500">Cargando historial...</p>}
      {error && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</p>}
      {!loading && !error && orders.length === 0 && <p className="py-8 text-sm text-slate-500">Todavía no hay órdenes registradas.</p>}
      {!loading && !error && orders.length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="border-b border-slate-200 text-slate-500"><th className="px-3 py-3 font-semibold">Producto</th><th className="px-3 py-3 font-semibold">SKU</th><th className="px-3 py-3 font-semibold">Cantidad</th><th className="px-3 py-3 font-semibold">Tipo de orden</th><th className="px-3 py-3 font-semibold">Fecha</th><th className="px-3 py-3 font-semibold">Creada por</th></tr></thead><tbody>{orders.map((order) => <tr key={`${order.direction}-${order.id}`} className="border-b border-slate-100 last:border-0"><td className="px-3 py-4 font-semibold text-slate-900">{order.product_name}</td><td className="px-3 py-4 text-slate-600">{order.product_sku}</td><td className="px-3 py-4 text-slate-700">{order.quantity}</td><td className="px-3 py-4"><span className={`rounded-full px-3 py-1 text-xs font-bold ${order.direction === "inbound" ? "bg-emerald-100 text-emerald-800" : "bg-orange-100 text-orange-800"}`}>{order.direction === "inbound" ? "Entrada" : "Salida"}</span></td><td className="px-3 py-4 text-slate-600">{new Date(order.created_at).toLocaleString("es-ES")}</td><td className="px-3 py-4 font-mono text-xs text-slate-600">{order.user_uuid}</td></tr>)}</tbody></table></div>}
    </section>
  </PageFrame>;
}