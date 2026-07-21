import { ApplyForm } from "@/components/apply-form";
import { SiteFooter } from "@/components/site-footer";
import Link from "next/link";

export default function ApplyPage() {
  return (
    <>
      <main className="brand-gradient relative isolate overflow-hidden py-10">
        <section className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8" aria-label="Introduccion del formulario">
          <Link href="/" className="text-sm font-semibold text-slate-700 underline">Volver al sitio</Link>
          <p
            className="mt-6 inline-flex rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-widest"
            style={{ borderColor: "rgb(10 59 138 / 20%)", color: "var(--brand-blue)" }}
          >
            Solicitud comercial B2B
          </p>
          <h1 className="mt-4 text-3xl font-extrabold leading-tight sm:text-4xl" style={{ color: "var(--brand-blue-deep)" }}>
            Cuentanos tu operacion y diseniamos tu plan TrackFlow
          </h1>
          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-slate-700 sm:text-base">
            Este registro nos ayuda a entender volumen, mercados, transportistas y prioridades
            operativas para construir una propuesta alineada con tu crecimiento.
          </p>
        </section>

        <section className="mx-auto mt-8 max-w-5xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-xl sm:p-8">
            <ApplyForm />
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
