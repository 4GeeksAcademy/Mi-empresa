"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { verifyToken } from "@/lib/auth";

// Rutas públicas que no requieren autenticación
const PUBLIC_ROUTES = ["/login", "/register"];

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (PUBLIC_ROUTES.includes(pathname)) {
      return;
    }

    if (!verifyToken()) {
      router.replace("/login");
    }
  }, [pathname, router]);

  // No renderizar nada en rutas públicas mientras el guard no aplica
  if (PUBLIC_ROUTES.includes(pathname)) {
    return <>{children}</>;
  }

  // Verificar token síncronamente para evitar flash
  if (!verifyToken()) {
    return null;
  }

  return <>{children}</>;
}