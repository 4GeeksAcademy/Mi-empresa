"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { telemetry, track, normalizedRoute } from "@/lib/telemetry";
import { getMe, getToken } from "@/lib/auth";
import { TelemetryErrorBoundary } from "@/components/telemetry-error-boundary";

export function TelemetryProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  useEffect(() => {
    telemetry.start();
    return () => telemetry.stop();
  }, []);
  useEffect(() => {
    const route = normalizedRoute(pathname);
    if (route === "/unknown") return;
    const section = route.includes("inventory") ? "inventory" : route.startsWith("/suppliers") ? "suppliers" : route.includes("incidents") ? "incidents" : route.startsWith("/account") ? "account" : route === "/login" ? "login" : route === "/register" ? "register" : "dashboard";
    let cancelled = false;
    async function captureSection() {
      const token = getToken();
      if (token) {
        try { await getMe(token); } catch { return; }
      }
      if (!cancelled) track("backoffice_section_viewed", { section, route });
    }
    void captureSection();
    return () => { cancelled = true; };
  }, [pathname]);
  return (
    <TelemetryErrorBoundary route={normalizedRoute(pathname)}>
      {children}
    </TelemetryErrorBoundary>
  );
}