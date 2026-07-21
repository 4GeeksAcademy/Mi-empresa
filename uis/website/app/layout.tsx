import type { Metadata } from "next";
import { Sora } from "next/font/google";
import "./globals.css";

const sora = Sora({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "TrackFlow | Logistica de ultima milla",
  description:
    "TrackFlow ayuda a marcas e-commerce a escalar su logistica con inventario unificado, tracking centralizado y devoluciones inteligentes.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className={sora.className}>{children}</body>
    </html>
  );
}
