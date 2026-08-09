import { KpiCard } from "@/components/kpi-card";
import { buildDashboardSnapshot } from "@/lib/trackflow-dashboard";
import Link from "next/link";

const snapshot = buildDashboardSnapshot();

const consultationRows = Object.entries(snapshot.report.consultasPorTipo);

export default function BackofficeHomePage() {
  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-teal-700">TrackFlow Backoffice</p>
          <h1 className="mt-2 text-3xl font-extrabold text-slate-900">Centro operativo de CX, tracking y devoluciones</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-600">
            Vista inicial para operaciones de dos paises (US/ES), con resultados calculados usando la logica de negocio TypeScript del Hito 2.
          </p>
          <Link
            href="/incidents-analysis"
            className="mt-4 inline-flex rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800"
          >
            Ir al analizador de incidencias
          </Link>
        </header>

        <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Pedidos totales" value={String(snapshot.report.totalPedidos)} hint="Base para seguimiento diario" />
          <KpiCard label="Consultas totales" value={String(snapshot.report.totalConsultas)} hint="B2B y consumidor final" />
          <KpiCard label="Consultas auto-resueltas" value={String(snapshot.consultasAutomaticas)} hint="Estado RESPONDIDA_AUTOMATICAMENTE" />
          <KpiCard label="Pedidos urgentes abiertos" value={String(snapshot.pedidosUrgentesNoEntregados)} hint="Riesgo operativo inmediato" />
        </section>

        <section className="mt-6 grid gap-4 xl:grid-cols-2">
          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-900">Resumen de logica integrada (Hito 2)</h2>
            <ul className="mt-4 space-y-2 text-sm text-slate-700">
              <li>Peso total de pedidos: {snapshot.report.pesoTotalKg.toFixed(1)} kg</li>
              <li>Peso promedio de pedidos: {snapshot.pesoPromedio.toFixed(2)} kg</li>
              <li>Estado del pedido P-1003 (busqueda lineal): {snapshot.pedidoBuscado}</li>
              <li>Devoluciones registradas: {snapshot.report.totalDevoluciones}</li>
              <li>Incidencias registradas: {snapshot.report.totalIncidencias}</li>
            </ul>
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-slate-900">Consultas por tipo</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="py-2 pr-4 font-semibold">Tipo</th>
                    <th className="py-2 font-semibold">Cantidad</th>
                  </tr>
                </thead>
                <tbody>
                  {consultationRows.map(([type, count]) => (
                    <tr key={type} className="border-b border-slate-100">
                      <td className="py-2 pr-4 font-medium text-slate-800">{type}</td>
                      <td className="py-2 text-slate-700">{count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900">Validaciones de datos</h2>
          <p className="mt-2 text-sm text-slate-600">
            Estas alertas salen de las funciones de validacion ya implementadas en src/utils/validations.ts.
          </p>

          {snapshot.validationIssues.length === 0 ? (
            <p className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">
              No se detectaron inconsistencias en los datos de ejemplo.
            </p>
          ) : (
            <div className="mt-4 space-y-3">
              {snapshot.validationIssues.map((issue) => (
                <article key={`${issue.entity}-${issue.id}`} className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                  <p className="text-sm font-bold text-amber-900">{issue.entity} {issue.id}</p>
                  <ul className="mt-1 list-disc pl-5 text-sm text-amber-800">
                    {issue.errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
