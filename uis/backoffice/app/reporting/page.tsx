"use client";

import { FormEvent, useEffect, useState } from "react";
import { getToken, handleUnauthorized } from "@/lib/auth";

type BusinessMetric = {
  metric_date: string;
  country_code: "US" | "ES";
  metric_code: string;
  currency_code: string;
  metric_value: string;
  numerator: string | null;
  denominator: string | null;
  unit: string;
  refreshed_at: string;
};

type KpiReport = {
  period: { from: string; to: string; end_exclusive: boolean };
  freshness: string | null;
  metrics: BusinessMetric[];
};

const KPI_LABELS: Record<string, string> = {
  shipment_volume: "Volumen de envíos",
  on_time_delivery_rate: "Tasa de entrega a tiempo",
  operating_cost_eur: "Coste operativo",
  returns_count: "Devoluciones",
  customer_satisfaction_csat: "Satisfacción del cliente (CSAT)",
};
const KPI_ORDER = Object.keys(KPI_LABELS);

function defaultPeriod() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  return { start: toDateInput(start), end: toDateInput(end) };
}

function toDateInput(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function shiftDate(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

async function requestKpis(startDate: string, endDate: string, countryCode: string) {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: shiftDate(endDate, 1),
  });
  if (countryCode) params.set("country_code", countryCode);
  const token = getToken();
  const response = await fetch(`/api/reporting/kpis?${params}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (response.status === 401) {
    handleUnauthorized();
    throw new Error("Tu sesión ha caducado. Inicia sesión de nuevo.");
  }
  if (response.status === 403) {
    throw new Error("Tu perfil no tiene permiso para consultar estos indicadores.");
  }
  if (!response.ok) {
    throw new Error("No se pudieron cargar los indicadores. Inténtalo de nuevo más tarde.");
  }
  return (await response.json()) as KpiReport;
}

function formatMetric(metric: BusinessMetric) {
  const value = Number(metric.metric_value);
  if (metric.metric_code === "on_time_delivery_rate") return `${value.toFixed(1)} %`;
  if (metric.metric_code === "customer_satisfaction_csat") return `${value.toFixed(2)} / 5`;
  if (metric.metric_code === "operating_cost_eur") {
    return new Intl.NumberFormat("es-ES", {
      style: "currency",
      currency: metric.currency_code,
      maximumFractionDigits: 2,
    }).format(value);
  }
  return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 }).format(value);
}

function metricExplanation(metric: BusinessMetric) {
  if (metric.metric_code === "on_time_delivery_rate" && metric.numerator && metric.denominator) {
    return `${Number(metric.numerator).toLocaleString("es-ES")} de ${Number(metric.denominator).toLocaleString("es-ES")} entregas elegibles`;
  }
  if (metric.metric_code === "customer_satisfaction_csat" && metric.denominator) {
    return `${Number(metric.denominator).toLocaleString("es-ES")} respuestas válidas`;
  }
  if (metric.metric_code === "operating_cost_eur" && metric.currency_code !== "EUR") {
    return `Importe en ${metric.currency_code}; no se ha aplicado conversión aprobada a EUR`;
  }
  return KPI_LABELS[metric.metric_code];
}

export default function ReportingPage() {
  const initialPeriod = defaultPeriod();
  const [startDate, setStartDate] = useState(initialPeriod.start);
  const [endDate, setEndDate] = useState(initialPeriod.end);
  const [countryCode, setCountryCode] = useState("");
  const [report, setReport] = useState<KpiReport | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [checkedAt, setCheckedAt] = useState(0);

  useEffect(() => {
    let active = true;
    requestKpis(initialPeriod.start, initialPeriod.end, "")
      .then((data) => {
        if (active) {
          setReport(data);
          setCheckedAt(Date.now());
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "No se pudieron cargar los indicadores.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [initialPeriod.end, initialPeriod.start]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (startDate >= endDate) {
      setError("La fecha final debe ser posterior a la fecha inicial.");
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      setReport(await requestKpis(startDate, endDate, countryCode));
      setCheckedAt(Date.now());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar los indicadores.");
    } finally {
      setIsLoading(false);
    }
  }

  const visibleMetrics = report?.metrics
    .filter((metric) => KPI_LABELS[metric.metric_code])
    .sort((left, right) =>
      KPI_ORDER.indexOf(left.metric_code) - KPI_ORDER.indexOf(right.metric_code)
      || left.metric_date.localeCompare(right.metric_date)
      || left.country_code.localeCompare(right.country_code),
    ) ?? [];
  const freshness = report?.freshness ? new Date(report.freshness) : null;
  const isStale = freshness !== null && checkedAt > 0
    && checkedAt - freshness.getTime() > 10 * 60 * 1000;

  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="border-b border-slate-300 pb-5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-teal-700">TrackFlow · Dirección</p>
          <h1 className="mt-2 text-3xl font-extrabold text-slate-900">Rendimiento del negocio</h1>
          <p className="mt-2 text-sm text-slate-600">Indicadores diarios de envíos, entregas, costes, devoluciones y satisfacción.</p>
        </header>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-wrap items-end gap-4 border-b border-slate-200 pb-5">
          <label className="grid gap-1 text-sm font-semibold text-slate-700">
            Desde
            <input className="rounded-md border border-slate-300 bg-white px-3 py-2 font-normal" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required />
          </label>
          <label className="grid gap-1 text-sm font-semibold text-slate-700">
            Hasta (inclusive)
            <input className="rounded-md border border-slate-300 bg-white px-3 py-2 font-normal" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} required />
          </label>
          <label className="grid gap-1 text-sm font-semibold text-slate-700">
            Operación
            <select className="rounded-md border border-slate-300 bg-white px-3 py-2 font-normal" value={countryCode} onChange={(event) => setCountryCode(event.target.value)}>
              <option value="">Estados Unidos y España</option>
              <option value="US">Estados Unidos</option>
              <option value="ES">España</option>
            </select>
          </label>
          <button className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60" type="submit" disabled={isLoading}>
            {isLoading ? "Consultando…" : "Actualizar indicadores"}
          </button>
        </form>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-2 text-sm text-slate-600" aria-live="polite">
          <p>
            Período: {report?.period.from ?? startDate} a {report ? shiftDate(report.period.to, -1) : endDate}.
          </p>
          {freshness && (
            <p className={isStale ? "font-semibold text-rose-700" : "font-semibold text-emerald-700"}>
              {isStale ? "Datos desactualizados" : "Datos actualizados"}: {freshness.toLocaleString("es-ES")}
            </p>
          )}
        </div>

        {error && <p role="alert" className="mt-5 border-l-4 border-rose-600 bg-rose-50 px-4 py-3 text-sm text-rose-900">{error}</p>}

        {isLoading && <p className="py-12 text-center text-sm text-slate-600">Cargando indicadores…</p>}

        {!isLoading && !error && visibleMetrics.length === 0 && (
          <div className="mt-6 border border-slate-200 bg-white px-5 py-8 text-center">
            <h2 className="text-lg font-bold text-slate-900">Todavía no hay indicadores publicados para este período</h2>
            <p className="mt-2 text-sm text-slate-600">Cuando las fuentes operativas estén conectadas y el pipeline complete una carga, los resultados aparecerán aquí.</p>
          </div>
        )}

        {!isLoading && !error && (
          <div className="mt-5 overflow-x-auto border border-slate-200 bg-white">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead className="bg-slate-100 text-slate-700">
                <tr>
                  <th className="px-4 py-3 font-semibold">Indicador</th>
                  <th className="px-4 py-3 font-semibold">Fecha</th>
                  <th className="px-4 py-3 font-semibold">Operación</th>
                  <th className="px-4 py-3 text-right font-semibold">Resultado</th>
                  <th className="px-4 py-3 font-semibold">Detalle</th>
                </tr>
              </thead>
              {KPI_ORDER.map((metricCode) => {
                const rows = visibleMetrics.filter((metric) => metric.metric_code === metricCode);
                return (
                  <tbody key={metricCode}>
                    <tr className="border-t border-slate-200 bg-slate-100">
                      <th className="px-4 py-2 font-bold text-slate-800" colSpan={5}>{KPI_LABELS[metricCode]}</th>
                    </tr>
                    {rows.length === 0 ? (
                      <tr>
                        <td className="px-4 py-3 text-slate-500" colSpan={5}>Sin datos publicados para este período</td>
                      </tr>
                    ) : rows.map((metric, index) => (
                      <tr key={`${metric.metric_date}-${metric.country_code}-${metric.currency_code}`} className={index % 2 ? "bg-slate-50" : "bg-white"}>
                        <td className="px-4 py-3 font-medium text-slate-900">{KPI_LABELS[metric.metric_code]}</td>
                        <td className="px-4 py-3 text-slate-700">{new Date(`${metric.metric_date}T00:00:00`).toLocaleDateString("es-ES", { timeZone: "UTC" })}</td>
                        <td className="px-4 py-3 text-slate-700">{metric.country_code === "US" ? "Estados Unidos" : "España"}</td>
                        <td className="px-4 py-3 text-right font-semibold tabular-nums text-slate-900">{formatMetric(metric)}</td>
                        <td className="px-4 py-3 text-slate-600">{metricExplanation(metric)}</td>
                      </tr>
                    ))}
                  </tbody>
                );
              })}
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
