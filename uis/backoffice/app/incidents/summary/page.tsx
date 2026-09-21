import dynamic from "next/dynamic";

const IncidentsSummary = dynamic(
  () => import("@/components/incidents-summary").then((module) => module.IncidentsSummary),
  {
    loading: () => <p className="rounded-2xl bg-white p-6 text-sm text-slate-500">Cargando resumen...</p>,
  },
);

export default function IncidentsSummaryPage() {
  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
        <IncidentsSummary />
      </section>
    </main>
  );
}