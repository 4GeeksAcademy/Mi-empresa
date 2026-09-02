"use client";

import { FormEvent, useMemo, useState } from "react";

interface Summary {
  total_processed: number;
  total_valid: number;
  total_invalid: number;
  invalid_breakdown: Record<string, number>;
  category_totals: Record<string, number>;
  status_totals: Record<string, number>;
  satisfaction_index_closed: number | null;
}

interface AnalyzeResponse {
  filename: string;
  summary: Summary;
}

export function IncidentsAnalyzer() {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  const categoryRows = useMemo(
    () => Object.entries(result?.summary.category_totals ?? {}),
    [result],
  );
  const statusRows = useMemo(
    () => Object.entries(result?.summary.status_totals ?? {}),
    [result],
  );
  const invalidRows = useMemo(
    () => Object.entries(result?.summary.invalid_breakdown ?? {}),
    [result],
  );

  function onPickFile(nextFile: File | null) {
    setFile(nextFile);
    setError(null);
  }

  async function onDownload() {
    setIsDownloading(true);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch("/api/incidents/results/export", { headers });
      if (!response.ok) {
        const errorBody = (await response.json()) as { detail?: string };
        throw new Error(errorBody.detail ?? "No se pudo descargar el fichero.");
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "results.csv";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError("Fallo inesperado durante la descarga.");
      }
    } finally {
      setIsDownloading(false);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!file) {
      setError("Debes seleccionar un fichero CSV.");
      return;
    }

    setIsLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch("/api/incidents/analyze", {
        method: "POST",
        headers,
        body: formData,
      });

      if (!response.ok) {
        const errorBody = (await response.json()) as { detail?: string };
        throw new Error(errorBody.detail ?? "No se pudo analizar el fichero.");
      }

      const payload = (await response.json()) as AnalyzeResponse;
      setResult(payload);
    } catch (caughtError) {
      setResult(null);
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError("Fallo inesperado durante el analisis.");
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="space-y-6">
      <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-extrabold text-slate-900">Analizador de incidencias</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Sube el CSV de incidencias para validar registros, excluir datos corruptos y calcular metricas operativas.
        </p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <label
            htmlFor="incident-csv"
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              const dropped = event.dataTransfer.files?.[0] ?? null;
              onPickFile(dropped);
            }}
            className={`flex min-h-40 cursor-pointer items-center justify-center rounded-xl border-2 border-dashed px-4 py-6 text-center transition ${
              isDragging
                ? "border-teal-600 bg-teal-50 text-teal-900"
                : "border-slate-300 bg-slate-50 text-slate-600 hover:border-teal-500"
            }`}
          >
            <input
              id="incident-csv"
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(event) => onPickFile(event.target.files?.[0] ?? null)}
            />
            <span className="text-sm font-semibold">
              {file ? `Archivo seleccionado: ${file.name}` : "Arrastra un CSV aqui o haz clic para seleccionarlo"}
            </span>
          </label>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={isLoading}
              className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? "Analizando..." : "Analizar fichero"}
            </button>

            <button
              type="button"
              onClick={onDownload}
              disabled={isDownloading}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isDownloading ? "Descargando..." : "Descargar results.csv"}
            </button>
          </div>

          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-800">{error}</p>}
        </form>
      </article>

      {result && (
        <section className="space-y-6">
          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-900">Resumen general</h2>
            <p className="mt-1 text-sm text-slate-500">Archivo: {result.filename}</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard label="Total procesados" value={String(result.summary.total_processed)} />
              <MetricCard label="Total validos" value={String(result.summary.total_valid)} />
              <MetricCard label="Total invalidos" value={String(result.summary.total_invalid)} />
              <MetricCard
                label="Satisfaccion media (cerrados)"
                value={
                  result.summary.satisfaction_index_closed === null
                    ? "N/A"
                    : result.summary.satisfaction_index_closed.toFixed(2)
                }
              />
            </div>
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-900">Invalidos por tipo de problema</h2>
            <SimpleTable
              emptyLabel="No se detectaron invalidos."
              rows={invalidRows}
              leftHeader="Problema"
              rightHeader="Cantidad"
            />
          </article>

          <article className="grid gap-6 xl:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-slate-900">Desglose por categoria</h2>
              <SimpleTable
                emptyLabel="No hay categorias para mostrar."
                rows={categoryRows}
                leftHeader="Categoria"
                rightHeader="Cantidad"
              />
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-slate-900">Desglose por estado</h2>
              <SimpleTable
                emptyLabel="No hay estados para mostrar."
                rows={statusRows}
                leftHeader="Estado"
                rightHeader="Cantidad"
              />
            </div>
          </article>
        </section>
      )}
    </section>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-extrabold text-slate-900">{value}</p>
    </div>
  );
}

function SimpleTable({
  rows,
  emptyLabel,
  leftHeader,
  rightHeader,
}: {
  rows: Array<[string, number]>;
  emptyLabel: string;
  leftHeader: string;
  rightHeader: string;
}) {
  if (rows.length === 0) {
    return <p className="mt-3 text-sm text-slate-500">{emptyLabel}</p>;
  }

  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            <th className="py-2 pr-4 font-semibold">{leftHeader}</th>
            <th className="py-2 font-semibold">{rightHeader}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, count]) => (
            <tr key={key} className="border-b border-slate-100">
              <td className="py-2 pr-4 font-medium text-slate-800">{key}</td>
              <td className="py-2 text-slate-700">{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
