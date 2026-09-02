"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { AuthGuard } from "@/components/auth-guard";

const PUBLIC_ROUTES = ["/login", "/register"];

export function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublic = PUBLIC_ROUTES.includes(pathname);

  return (
    <AuthGuard>
      {!isPublic && (
        <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
          <nav className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <Link
              href="/"
              className="rounded-md px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100"
            >
              Inicio
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
            <Link
              href="/account/profile"
              className="ml-auto rounded-md px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100"
            >
              Mi perfil
            </Link>
          </nav>
        </header>
      )}
      {children}
    </AuthGuard>
  );
}