import { SectionHeader } from "@/components/section-header";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

const features = [
  {
    title: "Inventario unificado",
    text: "Visibilidad de stock por SKU en Los Angeles y Zaragoza desde una sola capa operativa.",
  },
  {
    title: "Tracking centralizado",
    text: "Estado de envios en un endpoint unificado sin depender de multiples portales externos.",
  },
  {
    title: "Devoluciones inteligentes",
    text: "Automatizacion de aprobaciones y flujos de recogida con reglas por cliente.",
  },
  {
    title: "Dashboards accionables",
    text: "Indicadores de rendimiento para operaciones, transportistas, CX y direccion ejecutiva.",
  },
];

const benefits = [
  {
    title: "Menos incidencias",
    text: "Reducimos errores por procesos manuales y mejoramos la consistencia entre equipos y paises.",
  },
  {
    title: "Mayor velocidad",
    text: "Flujos automatizados de pedidos, tracking y devoluciones para acelerar cada etapa.",
  },
  {
    title: "Visibilidad completa",
    text: "Datos en tiempo real para decisiones mas rapidas en comercial, operaciones y direccion.",
  },
];

const steps = [
  {
    id: "Paso 1",
    title: "Conectamos tu operacion",
    text: "Integramos tus canales de venta, inventario y ordenes para centralizar la informacion critica.",
  },
  {
    id: "Paso 2",
    title: "Optimizamos cada envio",
    text: "Seleccionamos transportista, monitorizamos rutas y activamos alertas ante incidencias.",
  },
  {
    id: "Paso 3",
    title: "Cerramos el ciclo con datos",
    text: "Gestionamos devoluciones y reportes para mejorar coste, SLA y satisfaccion.",
  },
];

const experience = [
  {
    title: "15+ anos en el sector",
    text: "Desde 2009 acompanamos marcas que necesitan escalar operaciones exigentes sin perder control.",
  },
  {
    title: "Equipo binacional",
    text: "Operamos con equipos en Los Angeles y Zaragoza para coordinar ejecucion local con vision global.",
  },
  {
    title: "ADN orientado a datos",
    text: "Disenamos procesos medibles para mejorar conversion, rentabilidad y calidad de servicio.",
  },
];

export default function HomePage() {
  return (
    <>
      <SiteHeader />

      <main>
        <section id="inicio" className="brand-gradient relative overflow-hidden">
          <div className="mx-auto grid max-w-7xl gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:items-center lg:px-8 lg:py-24">
            <div>
              <p
                className="inline-flex rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-widest"
                style={{ borderColor: "rgb(10 59 138 / 20%)", color: "var(--brand-blue)" }}
              >
                TrackFlow Tech · Estados Unidos y Espana
              </p>
              <h1 className="mt-6 text-4xl font-extrabold leading-tight sm:text-5xl" style={{ color: "var(--brand-blue-deep)" }}>
                La logistica que tu e-commerce necesita para crecer sin fricciones
              </h1>
              <p className="mt-6 max-w-xl text-base leading-relaxed text-slate-700 sm:text-lg">
                Unificamos inventario, envios y devoluciones en una operacion inteligente de dos paises para que tus pedidos lleguen mas rapido.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-4">
                <a href="/apply" className="rounded-full px-6 py-3 text-sm font-bold text-white" style={{ backgroundColor: "var(--brand-blue)" }}>
                  Iniciar registro
                </a>
                <a href="#funcionamiento" className="rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-800">
                  Ver como funciona
                </a>
              </div>
            </div>

            <aside className="rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
              <h2 className="text-lg font-bold" style={{ color: "var(--brand-blue-deep)" }}>
                Impacto operativo en tiempo real
              </h2>
              <dl className="mt-6 grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl p-4" style={{ backgroundColor: "var(--brand-cream)" }}>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">Mercados activos</dt>
                  <dd className="mt-2 text-2xl font-extrabold" style={{ color: "var(--brand-blue-deep)" }}>2 paises</dd>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">Red de transportistas</dt>
                  <dd className="mt-2 text-2xl font-extrabold" style={{ color: "var(--brand-blue-deep)" }}>8 integraciones</dd>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">Cobertura operativa</dt>
                  <dd className="mt-2 text-2xl font-extrabold" style={{ color: "var(--brand-blue-deep)" }}>24/7</dd>
                </div>
                <div className="rounded-xl p-4" style={{ backgroundColor: "var(--brand-cream)" }}>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">Fundada en</dt>
                  <dd className="mt-2 text-2xl font-extrabold" style={{ color: "var(--brand-blue-deep)" }}>2009</dd>
                </div>
              </dl>
            </aside>
          </div>
        </section>

        <section id="caracteristicas" className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
          <SectionHeader eyebrow="Caracteristicas" title="Una plataforma operativa conectada" />
          <div className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {features.map((item) => (
              <article key={item.title} className="rounded-2xl border border-slate-200 p-6 shadow-sm">
                <h3 className="text-lg font-bold" style={{ color: "var(--brand-blue-deep)" }}>{item.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-slate-700">{item.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="beneficios" className="py-16 text-white" style={{ backgroundColor: "var(--brand-blue-deep)" }}>
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <SectionHeader dark eyebrow="Beneficios" title="Resultados que se sienten en la operacion diaria" />
            <div className="mt-10 grid gap-6 md:grid-cols-3">
              {benefits.map((item) => (
                <article key={item.title} className="rounded-2xl border border-white/20 bg-white/5 p-6">
                  <h3 className="text-xl font-bold">{item.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-slate-200">{item.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="funcionamiento" className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
          <SectionHeader eyebrow="Como funciona" title="Del pedido a la entrega, con una sola estrategia" />
          <ol className="mt-10 grid gap-6 md:grid-cols-3">
            {steps.map((step) => (
              <li key={step.id} className="rounded-2xl border border-slate-200 p-6">
                <p className="text-xs font-bold uppercase tracking-wide" style={{ color: "var(--brand-orange)" }}>{step.id}</p>
                <h3 className="mt-2 text-xl font-bold" style={{ color: "var(--brand-blue-deep)" }}>{step.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-slate-700">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="experiencia" className="bg-slate-50 py-16">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <SectionHeader eyebrow="Experiencia" title="Especialistas en logistica de alta complejidad" />
            <div className="mt-10 grid gap-6 md:grid-cols-3">
              {experience.map((item) => (
                <article key={item.title} className="rounded-2xl bg-white p-6 shadow-sm">
                  <h3 className="text-lg font-bold" style={{ color: "var(--brand-blue-deep)" }}>{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-700">{item.text}</p>
                </article>
              ))}
            </div>

            <div className="mt-10 rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
              <p className="text-lg font-semibold" style={{ color: "var(--brand-blue-deep)" }}>
                &quot;Necesitabamos una operacion mas rapida y trazable en dos paises. Con TrackFlow, la logistica dejo de ser un cuello de botella.&quot;
              </p>
              <p className="mt-3 text-sm font-medium text-slate-600">Director de Operaciones · Marca e-commerce internacional</p>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="rounded-3xl p-8 text-white sm:p-10" style={{ background: "linear-gradient(90deg, var(--brand-blue), var(--brand-blue-deep))" }}>
            <h2 className="text-3xl font-extrabold">Da el siguiente paso en tu operacion logistica</h2>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-100 sm:text-base">
              Cuentanos tu contexto, volumen y objetivos. Te proponemos un plan operativo adaptado a tu crecimiento.
            </p>
            <a href="/apply" className="mt-6 inline-flex rounded-full px-6 py-3 text-sm font-bold text-white" style={{ backgroundColor: "var(--brand-orange)" }}>
              Ir al formulario de aplicacion
            </a>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
