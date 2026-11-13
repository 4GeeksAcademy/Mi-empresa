import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/shell";
import { TelemetryProvider } from "@/components/telemetry-provider";

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
      <body>
        <TelemetryProvider>
          <Shell>{children}</Shell>
        </TelemetryProvider>
      </body>
    </html>
  );
}
