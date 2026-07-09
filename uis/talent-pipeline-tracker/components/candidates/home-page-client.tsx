"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CandidateFilters } from "@/components/candidates/candidate-filters";
import { CandidateForm } from "@/components/candidates/candidate-form";
import { CandidateTable } from "@/components/candidates/candidate-table";
import { createCandidate, getCandidates } from "@/services/candidates";
import {
  CandidateCreatePayload,
  CandidateRecord,
  CandidateStage,
  CandidateStatus,
} from "@/types/candidates";

function parseStatus(value: string | null): CandidateStatus | "" {
  if (!value) return "";
  if (["received", "in_progress", "selected", "discarded"].includes(value)) {
    return value as CandidateStatus;
  }
  return "";
}

function parseStage(value: string | null): CandidateStage | "" {
  if (!value) return "";
  if (
    ["pending", "review", "personal_interview", "technical_interview", "offer_presented"].includes(
      value,
    )
  ) {
    return value as CandidateStage;
  }
  return "";
}

export function HomePageClient() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const status = parseStatus(searchParams.get("status"));
  const stage = parseStage(searchParams.get("stage"));
  const search = searchParams.get("search") ?? "";

  const [records, setRecords] = useState<CandidateRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventMessage, setEventMessage] = useState<string | null>(null);

  const activeFilters = useMemo(
    () => ({
      status,
      stage,
      search,
      limit: 100,
    }),
    [search, stage, status],
  );

  const loadCandidates = useCallback(async () => {
    setError(null);
    setIsLoading(true);

    try {
      const payload = await getCandidates(activeFilters);
      setRecords(payload.data);
      setTotal(payload.total);
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "No se pudieron cargar las candidaturas.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [activeFilters]);

  function updateQuery(partial: Record<string, string>) {
    const params = new URLSearchParams(searchParams.toString());

    Object.entries(partial).forEach(([key, value]) => {
      if (value) params.set(key, value);
      else params.delete(key);
    });

    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadCandidates();
  }, [loadCandidates]);

  async function handleCreateCandidate(payload: CandidateCreatePayload) {
    await createCandidate(payload);
    setEventMessage("Nueva candidatura registrada correctamente.");
    await loadCandidates();
  }

  return (
    <main className="page-shell flex-1">
      <div className="mx-auto max-w-7xl px-4 py-6 md:py-10 space-y-5">
        <header className="card p-5">
          <p className="text-xs uppercase tracking-wide text-[var(--primary)] font-semibold">
            TrackFlow · People and Talent
          </p>
          <h1 className="mt-1 text-2xl md:text-3xl font-bold">Talent Pipeline Tracker</h1>
          <p className="mt-2 muted text-sm">
            Gestión interna de candidaturas para operaciones en Los Ángeles y Zaragoza.
          </p>
        </header>

        {eventMessage ? <p className="text-sm text-[var(--ok)]">{eventMessage}</p> : null}

        <CandidateFilters
          status={status}
          stage={stage}
          search={search}
          onStatusChange={(value) => updateQuery({ status: value })}
          onStageChange={(value) => updateQuery({ stage: value })}
          onSearchChange={(value) => updateQuery({ search: value })}
          onClear={() => {
            router.replace(pathname);
          }}
        />

        <CandidateTable records={records} total={total} loading={isLoading} error={error} />

        <CandidateForm
          mode="create"
          submitLabel="Registrar candidatura"
          onSubmit={handleCreateCandidate}
        />
      </div>
    </main>
  );
}
