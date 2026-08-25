import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const plex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "TrackFlow Backoffice",
  description: "Panel operativo interno de TrackFlow para CX, tracking y devoluciones.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className={plex.className}>
        <div className="min-h-screen">
          <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
            <nav className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
              <Link
                href="/"
                className="rounded-md px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100"
              >
                Inicio
              </Link>
              <Link
                href="/incidents"
                className="rounded-md px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100"
              >
                Incidencias
              </Link>
              <Link
                href="/incidents/new"
                className="rounded-md px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100"
              >
                Nueva incidencia
              </Link>
              <Link
                href="/incidents/summary"
                className="rounded-md px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100"
              >
                Resumen
              </Link>
              <Link
                href="/incidents-analysis"
                className="rounded-md px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100"
              >
                Analizador de incidencias
              </Link>
              <Link
                href="/suppliers"
                className="rounded-md px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100"
              >
                Directorio de proveedores
              </Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
