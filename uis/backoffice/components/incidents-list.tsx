"use client";

import { useCallback, useEffect, useState } from "react";

interface Incident {
  id: number;
  title: string;
  description: string;
  category: string;
  status: string;
  origin: string;
  branch: string;
  created_at: string;
  updated_at: string;
}

const STATUS_LABELS: Record<string, string> = {
  open: "Abierta",
  in_progress: "En progreso",
  resolved: "Resuelta",
  discarded: "Descartada",
};

const CATEGORY_LABELS: Record<string, string> = {
  logistica: "Logistica",
  tracking: "Tracking",
  devolucion: "Devolucion",
  facturacion: "Facturacion",
  soporte: "Soporte",
};

const ORIGIN_LABELS: Record<string, string> = {
  customer: "Cliente",
  branch: "Sede",
  internal: "Interno",
};

const BRANCH_LABELS: Record<string, string> = {
  "los-angeles": "Los Angeles",
  zaragoza: "Zaragoza",
  central: "Central",
};

const STATUS_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "open", label: "Abierta" },
  { value: "in_progress", label: "En progreso" },
  { value: "resolved", label: "Resuelta" },
  { value: "discarded", label: "Descartada" },
];

const ORIGIN_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "customer", label: "Cliente" },
  { value: "branch", label: "Sede" },
  { value: "internal", label: "Interno" },
];

const BRANCH_OPTIONS = [
  { value: "", label: "Todas" },
  { value: "los-angeles", label: "Los Angeles" },
  { value: "zaragoza", label: "Zaragoza" },
  { value: "central", label: "Central" },
];

const STATUS_COLORS: Record<string, string> = {
  open: "bg-amber-100 text-amber-800",
  in_progress: "bg-blue-100 text-blue-800",
  resolved: "bg-emerald-100 text-emerald-800",
  discarded: "bg-slate-100 text-slate-600",
};

const NEXT_STATUSES: Record<string, Array<{ value: string; label: string }>> = {
  open: [
    { value: "in_progress", label: "Marcar en progreso" },
    { value: "discarded", label: "Descartar" },
  ],
  in_progress: [
    { value: "resolved", label: "Marcar resuelta" },
    { value: "discarded", label: "Descartar" },
  ],
  resolved: [],
  discarded: [],
};

function formatDate(iso: string): string {
  try {
    const date = new Date(iso);
    return date.toLocaleDateString("es-ES", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function IncidentsList() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [originFilter, setOriginFilter] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [statusUpdateErrors, setStatusUpdateErrors] = useState<Record<number, string>>({});

  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const params = new URLSearchParams();
        if (statusFilter) params.set("status", statusFilter);
        if (originFilter) params.set("origin", originFilter);
        if (branchFilter) params.set("branch", branchFilter);
        const query = params.toString();
        const url = query ? `/api/incidents?${query}` : "/api/incidents";

        const response = await fetch(url);
        if (!response.ok) {
          throw new Error("No se pudieron cargar las incidencias.");
        }

        const data = (await response.json()) as Incident[];
        if (!cancelled) setIncidents(data);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Error al cargar las incidencias.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [statusFilter, originFilter, branchFilter, retryCount]);

  // Exponemos fetchIncidents para el boton de reintentar
  const retry = useCallback(() => {
    // Forzar re-ejecucion del efecto cambiando un estado interno
    setRetryCount((n) => n + 1);
  }, []);

  async function handleStatusChange(incidentId: number, newStatus: string) {
    // Guardar estado anterior para revertir si falla
    const previousIncidents = [...incidents];
    setStatusUpdateErrors((prev) => {
      const next = { ...prev };
      delete next[incidentId];
      return next;
    });

    // Optimistic update
    setIncidents((prev) =>
      prev.map((inc) =>
        inc.id === incidentId ? { ...inc, status: newStatus } : inc
      )
    );

    try {
      const response = await fetch(`/api/incidents/${incidentId}/status`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });

      if (!response.ok) {
        throw new Error("No se pudo actualizar el estado.");
      }
    } catch {
      // Revertir estado visual
      setIncidents(previousIncidents);
      setStatusUpdateErrors((prev) => ({
        ...prev,
        [incidentId]: "No se pudo actualizar el estado. Se ha restaurado el valor anterior.",
      }));

      // Limpiar el error despues de 5 segundos
      setTimeout(() => {
        setStatusUpdateErrors((prev) => {
          const next = { ...prev };
          delete next[incidentId];
          return next;
        });
      }, 5000);
    }
  }

  return (
    <section className="space-y-6">
      <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-extrabold text-slate-900">Incidencias</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Listado de todas las incidencias registradas en el sistema.
        </p>

        {/* Filtros */}
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="filter-status" className="block text-xs font-semibold text-slate-600">
              Estado
            </label>
            <select
              id="filter-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-200"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="filter-origin" className="block text-xs font-semibold text-slate-600">
              Origen
            </label>
            <select
              id="filter-origin"
              value={originFilter}
              onChange={(e) => setOriginFilter(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-200"
            >
              {ORIGIN_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="filter-branch" className="block text-xs font-semibold text-slate-600">
              Sede
            </label>
            <select
              id="filter-branch"
              value={branchFilter}
              onChange={(e) => setBranchFilter(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-200"
            >
              {BRANCH_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </article>

      {/* Estado de carga */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <svg className="h-8 w-8 animate-spin text-teal-600" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span className="ml-3 text-sm font-semibold text-slate-600">Cargando incidencias...</span>
        </div>
      )}

      {/* Estado de error */}
      {!loading && error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center">
          <p className="text-sm font-semibold text-rose-800">{error}</p>
          <button
            onClick={retry}
            className="mt-3 rounded-lg bg-rose-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-800"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Estado vacio */}
      {!loading && !error && incidents.length === 0 && (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-10 text-center">
          <p className="text-sm font-semibold text-slate-600">
            {statusFilter || originFilter || branchFilter
              ? "No hay incidencias que coincidan con los filtros seleccionados."
              : "No hay incidencias registradas aun."}
          </p>
        </div>
      )}

      {/* Listado */}
      {!loading && !error && incidents.length > 0 && (
        <div className="space-y-4">
          {incidents.map((incident) => (
            <article
              key={incident.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="text-base font-bold text-slate-900">{incident.title}</h3>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-600">{incident.description}</p>
                </div>
                <span
                  className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    STATUS_COLORS[incident.status] ?? "bg-slate-100 text-slate-700"
                  }`}
                >
                  {STATUS_LABELS[incident.status] ?? incident.status}
                </span>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                <span>
                  Categoria: <strong>{CATEGORY_LABELS[incident.category] ?? incident.category}</strong>
                </span>
                <span>
                  Origen: <strong>{ORIGIN_LABELS[incident.origin] ?? incident.origin}</strong>
                </span>
                <span>
                  Sede: <strong>{BRANCH_LABELS[incident.branch] ?? incident.branch}</strong>
                </span>
                <span>Creado: {formatDate(incident.created_at)}</span>
              </div>

              {/* Acciones de cambio de estado */}
              {NEXT_STATUSES[incident.status] && NEXT_STATUSES[incident.status].length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                  {NEXT_STATUSES[incident.status].map((next) => (
                    <button
                      key={next.value}
                      onClick={() => handleStatusChange(incident.id, next.value)}
                      className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-200"
                    >
                      {next.label}
                    </button>
                  ))}
                </div>
              )}

              {/* Error de actualizacion */}
              {statusUpdateErrors[incident.id] && (
                <p className="mt-2 text-xs font-medium text-rose-600">
                  {statusUpdateErrors[incident.id]}
                </p>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}