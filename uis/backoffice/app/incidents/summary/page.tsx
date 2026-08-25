import { IncidentsSummary } from "@/components/incidents-summary";

export default function IncidentsSummaryPage() {
  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
        <IncidentsSummary />
      </section>
    </main>
  );
}