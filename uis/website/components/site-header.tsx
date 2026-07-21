export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <a href="#inicio" className="text-xl font-extrabold" style={{ color: "var(--brand-blue-deep)" }}>
          TrackFlow
        </a>

        <nav aria-label="Navegacion principal" className="hidden lg:block">
          <ul className="flex items-center gap-6 text-sm font-semibold text-slate-700">
            <li><a href="#caracteristicas" className="hover:text-slate-900">Caracteristicas</a></li>
            <li><a href="#beneficios" className="hover:text-slate-900">Beneficios</a></li>
            <li><a href="#funcionamiento" className="hover:text-slate-900">Como funciona</a></li>
            <li><a href="#experiencia" className="hover:text-slate-900">Experiencia</a></li>
            <li><a href="#contacto" className="hover:text-slate-900">Contacto</a></li>
          </ul>
        </nav>

        <a
          href="/apply"
          className="rounded-full px-5 py-2.5 text-sm font-bold text-white"
          style={{ backgroundColor: "var(--brand-orange)" }}
        >
          Aplicar ahora
        </a>
      </div>
    </header>
  );
}
