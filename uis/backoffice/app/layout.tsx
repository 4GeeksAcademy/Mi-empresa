import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { Shell } from "@/components/shell";
import { TelemetryProvider } from "@/components/telemetry-provider";

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
        <TelemetryProvider>
          <Shell>{children}</Shell>
        </TelemetryProvider>
      </body>
    </html>
  );
}
