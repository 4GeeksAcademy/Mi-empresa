"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type SupplierCountry = "US" | "ES";
type SupplierStatus = "activo" | "suspendido";
type SupplierCategory =
  | "transporte"
  | "embalaje"
  | "almacenaje"
  | "devoluciones"
  | "tecnologia";

interface Supplier {
  id: number;
  nombre: string;
  pais: SupplierCountry;
  categorias_producto: SupplierCategory[];
  tarifa_por_kg: number;
  status: SupplierStatus;
  updated_at: string;
}

interface SupplierCreatePayload {
  nombre: string;
  pais: SupplierCountry;
  categorias_producto: SupplierCategory[];
  tarifa_por_kg: number;
  status: SupplierStatus;
}

const CATEGORIES: Array<{ value: SupplierCategory; label: string }> = [
  { value: "transporte", label: "Transporte" },
  { value: "embalaje", label: "Embalaje" },
  { value: "almacenaje", label: "Almacenaje" },
  { value: "devoluciones", label: "Devoluciones" },
  { value: "tecnologia", label: "Tecnologia" },
];

function parseErrorDetail(errorBody: unknown): string {
  if (typeof errorBody !== "object" || errorBody === null) {
    return "Error inesperado en la solicitud.";
  }

  if ("detail" in errorBody && typeof errorBody.detail === "string") {
    return errorBody.detail;
  }

  if ("detail" in errorBody && Array.isArray(errorBody.detail)) {
    return "Datos invalidos. Revisa los campos e intenta de nuevo.";
  }

  return "Error inesperado en la solicitud.";
}

export function SuppliersDirectory() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [countryFilter, setCountryFilter] = useState<"" | SupplierCountry>("");
  const [categoryFilter, setCategoryFilter] = useState<"" | SupplierCategory>("");

  const [newName, setNewName] = useState("");
  const [newCountry, setNewCountry] = useState<SupplierCountry>("US");
  const [newCategories, setNewCategories] = useState<SupplierCategory[]>(["transporte"]);
  const [newRate, setNewRate] = useState("5");
  const [newStatus, setNewStatus] = useState<SupplierStatus>("activo");

  const [draftRates, setDraftRates] = useState<Record<number, string>>({});

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (countryFilter) params.set("pais", countryFilter);
    if (categoryFilter) params.set("categoria", categoryFilter);
    return params.toString();
  }, [countryFilter, categoryFilter]);

  const fetchSuppliers = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(query ? `/api/suppliers?${query}` : "/api/suppliers");
      if (!response.ok) {
        const body = (await response.json()) as unknown;
        throw new Error(parseErrorDetail(body));
      }

      const payload = (await response.json()) as Supplier[];
      setSuppliers(payload);
      setDraftRates(
        payload.reduce<Record<number, string>>((acc, supplier) => {
          acc[supplier.id] = supplier.tarifa_por_kg.toString();
          return acc;
        }, {}),
      );
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError("No se pudo cargar el directorio de proveedores.");
      }
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    // Carga inicial y recarga al cambiar filtros; sincroniza estado con API externa.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchSuppliers();
  }, [fetchSuppliers]);

  function toggleCategorySelection(category: SupplierCategory, checked: boolean) {
    setNewCategories((current) => {
      if (checked) {
        if (current.includes(category)) return current;
        return [...current, category];
      }
      return current.filter((item) => item !== category);
    });
  }

  async function handleCreateSupplier(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    const parsedRate = Number(newRate);
    if (!Number.isFinite(parsedRate) || parsedRate <= 0) {
      setError("La tarifa por kg debe ser un numero mayor que cero.");
      return;
    }

    if (newCategories.length === 0) {
      setError("Debes seleccionar al menos una categoria.");
      return;
    }

    const payload: SupplierCreatePayload = {
      nombre: newName,
      pais: newCountry,
      categorias_producto: newCategories,
      tarifa_por_kg: parsedRate,
      status: newStatus,
    };

    try {
      const response = await fetch("/api/suppliers", {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const body = (await response.json()) as unknown;
        throw new Error(parseErrorDetail(body));
      }

      setMessage("Proveedor registrado correctamente.");
      setNewName("");
      setNewRate("5");
      setNewCountry("US");
      setNewStatus("activo");
      setNewCategories(["transporte"]);
      await fetchSuppliers();
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError("No se pudo crear el proveedor.");
      }
    }
  }

  async function handleUpdateRate(id: number) {
    setError(null);
    setMessage(null);

    const parsedRate = Number(draftRates[id] ?? "");
    if (!Number.isFinite(parsedRate) || parsedRate <= 0) {
      setError("La tarifa por kg debe ser un numero mayor que cero.");
      return;
    }

    try {
      const response = await fetch(`/api/suppliers/${id}/rate`, {
        method: "PATCH",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify({ tarifa_por_kg: parsedRate }),
      });

      if (!response.ok) {
        const body = (await response.json()) as unknown;
        throw new Error(parseErrorDetail(body));
      }

      setMessage("Tarifa actualizada.");
      await fetchSuppliers();
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError("No se pudo actualizar la tarifa.");
      }
    }
  }

  async function handleToggleStatus(supplier: Supplier) {
    setError(null);
    setMessage(null);

    const nextStatus: SupplierStatus = supplier.status === "activo" ? "suspendido" : "activo";

    try {
      const response = await fetch(`/api/suppliers/${supplier.id}/status`, {
        method: "PATCH",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify({ status: nextStatus }),
      });

      if (!response.ok) {
        const body = (await response.json()) as unknown;
        throw new Error(parseErrorDetail(body));
      }

      setMessage("Estado actualizado.");
      await fetchSuppliers();
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError("No se pudo actualizar el estado.");
      }
    }
  }

  return (
    <section className="space-y-6">
      <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-extrabold text-slate-900">Directorio de proveedores</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Gestiona proveedores por pais y categoria, actualiza tarifas por kg y controla su estado operativo.
        </p>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="text-sm font-semibold text-slate-700">
            Filtrar por pais
            <select
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={countryFilter}
              onChange={(event) => setCountryFilter(event.target.value as "" | SupplierCountry)}
            >
              <option value="">Todos</option>
              <option value="US">US</option>
              <option value="ES">ES</option>
            </select>
          </label>

          <label className="text-sm font-semibold text-slate-700">
            Filtrar por categoria
            <select
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value as "" | SupplierCategory)}
            >
              <option value="">Todas</option>
              {CATEGORIES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </article>

      <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-900">Registrar proveedor</h2>
        <form onSubmit={handleCreateSupplier} className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="text-sm font-semibold text-slate-700 md:col-span-2">
            Nombre
            <input
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              required
            />
          </label>

          <label className="text-sm font-semibold text-slate-700">
            Pais
            <select
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={newCountry}
              onChange={(event) => setNewCountry(event.target.value as SupplierCountry)}
            >
              <option value="US">US</option>
              <option value="ES">ES</option>
            </select>
          </label>

          <label className="text-sm font-semibold text-slate-700">
            Tarifa por kg
            <input
              type="number"
              min="0.01"
              step="0.01"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={newRate}
              onChange={(event) => setNewRate(event.target.value)}
              required
            />
          </label>

          <label className="text-sm font-semibold text-slate-700 md:col-span-2">
            Estado
            <select
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={newStatus}
              onChange={(event) => setNewStatus(event.target.value as SupplierStatus)}
            >
              <option value="activo">Activo</option>
              <option value="suspendido">Suspendido</option>
            </select>
          </label>

          <fieldset className="md:col-span-2">
            <legend className="text-sm font-semibold text-slate-700">Categorias de producto</legend>
            <div className="mt-2 flex flex-wrap gap-3">
              {CATEGORIES.map((option) => (
                <label
                  key={option.value}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700"
                >
                  <input
                    type="checkbox"
                    checked={newCategories.includes(option.value)}
                    onChange={(event) => toggleCategorySelection(option.value, event.target.checked)}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="md:col-span-2">
            <button
              type="submit"
              className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800"
            >
              Crear proveedor
            </button>
          </div>
        </form>
      </article>

      {error && <p className="rounded-lg bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-800">{error}</p>}
      {message && <p className="rounded-lg bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">{message}</p>}

      <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-900">Listado</h2>

        {loading ? (
          <p className="mt-3 text-sm text-slate-500">Cargando proveedores...</p>
        ) : suppliers.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No hay proveedores para los filtros seleccionados.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 pr-4 font-semibold">Proveedor</th>
                  <th className="py-2 pr-4 font-semibold">Pais</th>
                  <th className="py-2 pr-4 font-semibold">Categorias</th>
                  <th className="py-2 pr-4 font-semibold">Tarifa por kg</th>
                  <th className="py-2 pr-4 font-semibold">Estado</th>
                  <th className="py-2 pr-4 font-semibold">Actualizado</th>
                  <th className="py-2 font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier) => (
                  <tr key={supplier.id} className="border-b border-slate-100 align-top">
                    <td className="py-3 pr-4 font-semibold text-slate-900">{supplier.nombre}</td>
                    <td className="py-3 pr-4 text-slate-700">{supplier.pais}</td>
                    <td className="py-3 pr-4 text-slate-700">{supplier.categorias_producto.join(", ")}</td>
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          step="0.01"
                          min="0.01"
                          value={draftRates[supplier.id] ?? supplier.tarifa_por_kg.toString()}
                          onChange={(event) =>
                            setDraftRates((current) => ({
                              ...current,
                              [supplier.id]: event.target.value,
                            }))
                          }
                          className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
                        />
                        <button
                          type="button"
                          onClick={() => void handleUpdateRate(supplier.id)}
                          className="rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400"
                        >
                          Guardar
                        </button>
                      </div>
                    </td>
                    <td className="py-3 pr-4">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold ${
                          supplier.status === "activo"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {supplier.status}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-slate-600">{new Date(supplier.updated_at).toLocaleString("es-ES")}</td>
                    <td className="py-3">
                      <button
                        type="button"
                        onClick={() => void handleToggleStatus(supplier)}
                        className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
                      >
                        {supplier.status === "activo" ? "Suspender" : "Activar"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
