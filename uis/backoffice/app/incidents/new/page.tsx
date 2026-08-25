import { IncidentForm } from "@/components/incident-form";

export default function NewIncidentPage() {
  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
        <IncidentForm />
      </section>
    </main>
  );
}