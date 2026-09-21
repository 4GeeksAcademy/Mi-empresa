import dynamic from "next/dynamic";

const IncidentsAnalyzer = dynamic(
  () => import("@/components/incidents-analyzer").then((module) => module.IncidentsAnalyzer),
  {
    loading: () => <p className="rounded-2xl bg-white p-6 text-sm text-slate-500">Cargando analizador...</p>,
  },
);

export default function IncidentsAnalysisPage() {
  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <IncidentsAnalyzer />
      </section>
    </main>
  );
}
