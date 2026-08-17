import { SuppliersDirectory } from "@/components/suppliers-directory";

export default function SuppliersPage() {
  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <SuppliersDirectory />
      </section>
    </main>
  );
}
