export function SiteFooter() {
  return (
    <footer id="contacto" className="bg-slate-950 text-slate-200">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-2 lg:px-8">
        <div>
          <h2 className="text-2xl font-extrabold text-white">TrackFlow</h2>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-slate-300">
            Logistica de ultima milla y gestion de almacenes para marcas e-commerce que
            quieren escalar con eficiencia, control y visibilidad total.
          </p>
        </div>

        <address className="not-italic text-sm text-slate-300">
          <h3 className="text-lg font-bold text-white">Contacto</h3>
          <p className="mt-3">Email: sales@trackflow.com</p>
          <p>Telefono: +1 213 555 0149</p>
          <p>Los Angeles, Estados Unidos</p>
          <p>Zaragoza, Espana</p>
        </address>
      </div>

      <div className="border-t border-slate-800 px-4 py-4 text-center text-xs text-slate-400 sm:px-6 lg:px-8">
        <p>© {new Date().getFullYear()} TrackFlow. Todos los derechos reservados.</p>
      </div>
    </footer>
  );
}
