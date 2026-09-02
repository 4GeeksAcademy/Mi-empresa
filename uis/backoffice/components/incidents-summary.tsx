"use client";

import { useCallback, useEffect, useState } from "react";

interface SummaryData {
  total_incidents: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_origin: Record<string, number>;
  by_branch: Record<string, number>;
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

const STATUS_COLORS: Record<string, string> = {
  open: "bg-amber-100 text-amber-800",
  in_progress: "bg-blue-100 text-blue-800",
  resolved: "bg-emerald-100 text-emerald-800",
  discarded: "bg-slate-100 text-slate-600",
};

const CATEGORY_COLORS: Record<string, string> = {
  logistica: "bg-indigo-100 text-indigo-800",
  tracking: "bg-cyan-100 text-cyan-800",
  devolucion: "bg-violet-100 text-violet-800",
  facturacion: "bg-orange-100 text-orange-800",
  soporte: "bg-pink-100 text-pink-800",
};

function SummaryChart({ items, labelMap, colorMap }: {
  items: Record<string, number>;
  labelMap: Record<string, string>;
  colorMap?: Record<string, string>;
}) {
  const entries = Object.entries(items);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);

  if (entries.length === 0) {
    return <p className="text-sm text-slate-500">Sin datos</p>;
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, count]) => {
        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
        const colorClass = colorMap?.[key] ?? "bg-teal-100 text-teal-800";
        return (
          <div key={key}>
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${colorClass}`}>
                  {labelMap[key] ?? key}
                </span>
              </div>
              <span className="font-semibold text-slate-800">
                {count}
                <span className="ml-1 text-xs font-normal text-slate-500">({pct}%)</span>
              </span>
            </div>
            <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-teal-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
      <div className="pt-1 text-right text-xs font-semibold text-slate-600">
        Total: {total}
      </div>
    </div>
  );
}

export function IncidentsSummary() {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch("/api/incidents/summary");
        if (!response.ok) {
          throw new Error("No se pudo obtener el resumen de incidencias.");
        }
        const data = (await response.json()) as SummaryData;
        if (!cancelled) setSummary(data);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Error al cargar el resumen.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  const retry = useCallback(() => setRetryCount((n) => n + 1), []);

  return (
    <section className="space-y-6">
      <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-extrabold text-slate-900">Resumen de incidencias</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Metricas agregadas de todas las incidencias registradas en el sistema.
        </p>
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
          <span className="ml-3 text-sm font-semibold text-slate-600">Cargando resumen...</span>
        </div>
      )}

      {/* Estado de error */}
      {!loading && error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-8 text-center">
          <p className="text-sm font-semibold text-rose-800">{error}</p>
          <button
            onClick={retry}
            className="mt-3 rounded-lg bg-rose-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-800"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Panel de metricas */}
      {!loading && !error && summary && (
        <>
          {/* Total general */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="text-center">
              <p className="text-4xl font-extrabold text-teal-700">{summary.total_incidents}</p>
              <p className="mt-1 text-sm font-semibold text-slate-600">Total de incidencias</p>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            {/* Por estado */}
            <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-bold text-slate-900">Por estado</h2>
              <SummaryChart
                items={summary.by_status}
                labelMap={STATUS_LABELS}
                colorMap={STATUS_COLORS}
              />
            </article>

            {/* Por categoria */}
            <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-bold text-slate-900">Por categoria</h2>
              <SummaryChart
                items={summary.by_category}
                labelMap={CATEGORY_LABELS}
                colorMap={CATEGORY_COLORS}
              />
            </article>

            {/* Por origen */}
            <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-bold text-slate-900">Por origen</h2>
              <SummaryChart
                items={summary.by_origin}
                labelMap={ORIGIN_LABELS}
              />
            </article>

            {/* Por sede */}
            <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-bold text-slate-900">Por sede</h2>
              <SummaryChart
                items={summary.by_branch}
                labelMap={BRANCH_LABELS}
              />
            </article>
          </div>
        </>
      )}
    </section>
  );
}