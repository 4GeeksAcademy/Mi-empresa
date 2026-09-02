"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { verifyToken } from "@/lib/auth";

const PUBLIC_ROUTES = ["/login", "/register", "/forgot-password", "/reset-password"];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_ROUTES.includes(pathname);

  // verifyToken es síncrono: lo evaluamos directamente si no es ruta pública
  const [checked] = useState(() => {
    if (typeof window === "undefined") return false;
    return isPublic || verifyToken();
  });

  useEffect(() => {
    if (!isPublic && !checked) {
      router.replace("/login");
    }
  }, [pathname, router, isPublic, checked]);

  if (!isPublic && !checked) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col">
      {isPublic && (
        <header
          className="border-b px-4 py-3"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
        >
          <nav className="mx-auto flex max-w-7xl items-center gap-4">
            <Link
              href="/login"
              className="text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              Login
            </Link>
            <Link
              href="/register"
              className="text-sm font-semibold"
              style={{ color: "var(--primary)" }}
            >
              Registro
            </Link>
          </nav>
        </header>
      )}
      {!isPublic && (
        <header
          className="border-b px-4 py-3"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
        >
          <nav className="mx-auto flex max-w-7xl items-center gap-4">
            <Link
              href="/"
              className="text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              Candidatos
            </Link>
            <Link
              href="/account/profile"
              className="ml-auto text-sm font-semibold"
              style={{ color: "var(--primary)" }}
            >
              Mi perfil
            </Link>
          </nav>
        </header>
      )}
      {children}
    </div>
  );
}