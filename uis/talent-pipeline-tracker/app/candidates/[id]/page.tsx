"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CandidateForm } from "@/components/candidates/candidate-form";
import { CandidateNotes } from "@/components/candidates/candidate-notes";
import { STAGE_OPTIONS, STATUS_OPTIONS, getStageLabel, getStatusLabel } from "@/lib/candidate-domain";
import { formatDate } from "@/lib/format";
import { getCandidateById, patchCandidate, replaceCandidate } from "@/services/candidates";
import { CandidateCreatePayload, CandidateRecord, CandidateStage, CandidateStatus } from "@/types/candidates";

export default function CandidateDetailPage() {
  const params = useParams<{ id: string }>();
  const recordId = params.id;

  const [record, setRecord] = useState<CandidateRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusValue, setStatusValue] = useState<CandidateStatus | "">("");
  const [stageValue, setStageValue] = useState<CandidateStage | "">("");
  const [patchLoading, setPatchLoading] = useState(false);
  const [patchMessage, setPatchMessage] = useState<string | null>(null);

  const loadRecord = useCallback(async () => {
    if (!recordId) return;

    setError(null);
    setLoading(true);
    try {
      const payload = await getCandidateById(recordId);
      setRecord(payload);
      setStatusValue(payload.status);
      setStageValue(payload.stage);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "No se pudo cargar la candidatura.");
    } finally {
      setLoading(false);
    }
  }, [recordId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadRecord();
  }, [loadRecord]);

  async function handlePatch(field: "status" | "stage") {
    if (!record) return;

    setPatchMessage(null);
    setPatchLoading(true);

    try {
      const payload =
        field === "status"
          ? await patchCandidate(record.id, { status: statusValue as CandidateStatus })
          : await patchCandidate(record.id, { stage: stageValue as CandidateStage });

      setRecord(payload);
      setPatchMessage(
        field === "status" ? "Estado actualizado correctamente." : "Etapa actualizada correctamente.",
      );
    } catch (patchError) {
      setPatchMessage(patchError instanceof Error ? patchError.message : "No se pudo actualizar.");
    } finally {
      setPatchLoading(false);
    }
  }

  async function handleReplace(payload: CandidateCreatePayload) {
    if (!record) return;
    const updated = await replaceCandidate(record.id, payload);
    setRecord(updated);
  }

  return (
    <main className="page-shell flex-1">
      <div className="mx-auto max-w-7xl px-4 py-6 md:py-10 space-y-5">
        <header className="card p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--primary)] font-semibold">
                TrackFlow · People and Talent
              </p>
              <h1 className="mt-1 text-2xl font-bold">Detalle de candidatura</h1>
            </div>
            <Link href="/" className="btn btn-secondary">
              Volver al listado
            </Link>
          </div>
        </header>

        {loading ? <p>Cargando detalle...</p> : null}
        {error ? <p className="text-[var(--danger)]">{error}</p> : null}

        {!loading && record ? (
          <>
            <section className="card p-4">
              <h2 className="text-lg font-semibold mb-3">Resumen</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <p>
                  <strong>Nombre:</strong> {record.full_name}
                </p>
                <p>
                  <strong>Email:</strong> {record.email}
                </p>
                <p>
                  <strong>Teléfono:</strong> {record.phone}
                </p>
                <p>
                  <strong>Puesto:</strong> {record.position}
                </p>
                <p>
                  <strong>LinkedIn:</strong> {record.linkedin_url ?? "Sin enlace"}
                </p>
                <p>
                  <strong>CV:</strong> {record.cv_url ?? "Sin enlace"}
                </p>
                <p>
                  <strong>Experiencia:</strong> {record.experience_years} años
                </p>
                <p>
                  <strong>Aplicó:</strong> {formatDate(record.applied_at)}
                </p>
                <p>
                  <strong>Estado actual:</strong> {getStatusLabel(record.status)}
                </p>
                <p>
                  <strong>Etapa actual:</strong> {getStageLabel(record.stage)}
                </p>
              </div>
            </section>

            <section className="card p-4 space-y-3">
              <h2 className="text-lg font-semibold">Actualizar estado y etapa</h2>
              {patchMessage ? <p className="text-sm muted">{patchMessage}</p> : null}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-2">
                  <label className="text-sm block">Estado</label>
                  <div className="flex items-center gap-2">
                    <select
                      className="input"
                      value={statusValue}
                      onChange={(event) => setStatusValue(event.target.value as CandidateStatus)}
                    >
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        void handlePatch("status");
                      }}
                      disabled={patchLoading}
                    >
                      Guardar
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-sm block">Etapa</label>
                  <div className="flex items-center gap-2">
                    <select
                      className="input"
                      value={stageValue}
                      onChange={(event) => setStageValue(event.target.value as CandidateStage)}
                    >
                      {STAGE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        void handlePatch("stage");
                      }}
                      disabled={patchLoading}
                    >
                      Guardar
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <CandidateForm
              mode="edit"
              initialValue={record}
              submitLabel="Guardar cambios"
              onSubmit={handleReplace}
            />

            <CandidateNotes recordId={record.id} />
          </>
        ) : null}
      </div>
    </main>
  );
}
