import { Suspense } from "react";
import { HomePageClient } from "@/components/candidates/home-page-client";

export default function HomePage() {
  return (
    <Suspense fallback={<main className="page-shell flex-1 p-6">Cargando panel...</main>}>
      <HomePageClient />
    </Suspense>
  );
}
