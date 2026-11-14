"use client";

import { useCallback, useEffect, useState } from "react";

type DepartmentApproval = {
  department_id: string;
  approver: string;
  section_id: string | null;
  approval_status: string;
  decision: null | { decision: string; comment: string; decided_at: string };
  draft_excerpt: string;
  evaluation: { overall_pass: boolean | null; score: number | null; violations: string[] };
  open_questions: string[];
  flags: { needs_human_review: boolean; iteration_limit_reached: boolean; arbitration_blocked: boolean };
  rework_runs: number | null;
  round: number | null;
  pending_interrupt: boolean;
  interrupt_id: string | null;
  thread_id: string;
};

type ApprovalsSnapshot = {
  ticket_id: string;
  status: string;
  pending: string[];
  departments: DepartmentApproval[];
  final_document: null | { content: string; currency?: string; generated_at?: string };
};

const DECISIONS = [
  { value: "aprobar", label: "Aprobar", style: "bg-emerald-700" },
  { value: "request_changes", label: "Pedir cambios", style: "bg-amber-600" },
  { value: "rechazar", label: "Rechazar", style: "bg-red-700" },
] as const;

export function RfpApprovals({ ticketId, status }: { ticketId: string; status: string }) {
  const [snapshot, setSnapshot] = useState<ApprovalsSnapshot | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [openExcerpt, setOpenExcerpt] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    const response = await fetch(`/api/rfps/${encodeURIComponent(ticketId)}/approvals`);
    if (!response.ok) return;
    setSnapshot((await response.json()) as ApprovalsSnapshot);
  }, [ticketId]);

  useEffect(() => {
    if (status === "analizando" || status === "analisis_completo" || status === "generando_borrador") return;
    const initialRefresh = window.setTimeout(() => { void refresh(); }, 0);
    if (status !== "esperando_aprobación") {
      return () => window.clearTimeout(initialRefresh);
    }
    const timer = window.setInterval(() => { void refresh(); }, 2000);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(timer);
    };
  }, [ticketId, status, refresh]);

  async function startApprovals() {
    setError("");
    setBusy(true);
    try {
      const response = await fetch(`/api/rfps/${encodeURIComponent(ticketId)}/approvals`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "No se pudieron iniciar las aprobaciones.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo iniciar la aprobación.");
    } finally {
      setBusy(false);
    }
  }

  async function decide(department: DepartmentApproval, decision: (typeof DECISIONS)[number]["value"]) {
    setError("");
    const comment = (comments[department.department_id] ?? "").trim();
    if (decision !== "aprobar" && !comment) {
      setError(`El comentario es obligatorio para ${decision === "rechazar" ? "rechazar" : "pedir cambios"}.`);
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(
        `/api/rfps/${encodeURIComponent(ticketId)}/approvals/${encodeURIComponent(department.department_id)}`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            decision,
            approver: department.approver,
            comment,
            interrupt_id: department.interrupt_id,
          }),
        },
      );
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "No se pudo registrar la decisión.");
      setComments((current) => ({ ...current, [department.department_id]: "" }));
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo registrar la decisión.");
    } finally {
      setBusy(false);
    }
  }

  if (status === "needs_human_review" || status === "en_evaluación") {
    return (
      <div className="space-y-2 border-t border-slate-200 pt-4">
        <p className="text-sm text-slate-600">Borradores evaluados listos para aprobación humana por responsable.</p>
        <button
          onClick={startApprovals}
          disabled={busy}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          Iniciar aprobaciones
        </button>
      </div>
    );
  }

  if (!snapshot) {
    if (error) return <p role="alert" className="text-sm text-red-700">{error}</p>;
    return null;
  }

  return (
    <div className="space-y-4 border-t border-slate-200 pt-4" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold">Aprobación humana por responsable</h2>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
          {snapshot.status} · pendientes: {snapshot.pending.length || "ninguno"}
        </span>
      </div>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        {snapshot.departments.map((department) => (
          <article
            key={department.department_id}
            className={`space-y-2 rounded-md border p-3 ${
              department.approval_status === "aprobado"
                ? "border-emerald-300 bg-emerald-50"
                : "border-slate-200 bg-slate-50"
            }`}
          >
            <header className="flex items-center justify-between text-sm">
              <span className="font-semibold">{department.department_id} — {department.approver}</span>
              <span className="rounded bg-white px-2 py-0.5 text-xs text-slate-600">{department.approval_status}</span>
            </header>
            {/* Datos mínimos: sin releer el documento completo */}
            <p className="text-xs text-slate-600">
              Evaluación: {department.evaluation.overall_pass === null ? "sin dato" : department.evaluation.overall_pass ? "conforme" : "no conforme"}
              {department.evaluation.score !== null && ` · score ${department.evaluation.score}`}
              {department.rework_runs ? ` · rework ${department.rework_runs}` : ""}
            </p>
            {department.evaluation.violations.length > 0 && (
              <p className="text-xs text-red-700">Incumplimientos: {department.evaluation.violations.join(", ")}</p>
            )}
            {department.open_questions.length > 0 && (
              <p className="text-xs text-slate-700">Preguntas abiertas: {department.open_questions.join("; ")}</p>
            )}
            {department.flags.needs_human_review && (
              <p className="text-xs font-medium text-amber-700">
                Requiere revisión humana
                {department.flags.iteration_limit_reached ? " · límite de iteraciones agotado" : ""}
                {department.flags.arbitration_blocked ? " · bloqueado por arbitraje" : ""}
              </p>
            )}
            <button
              type="button"
              className="text-xs text-slate-500 underline"
              onClick={() => setOpenExcerpt((current) => ({ ...current, [department.department_id]: !current[department.department_id] }))}
            >
              {openExcerpt[department.department_id] ? "Ocultar borrador" : "Ver extracto del borrador"}
            </button>
            {openExcerpt[department.department_id] && (
              <p className="max-h-40 overflow-y-auto rounded bg-white p-2 text-xs text-slate-700">{department.draft_excerpt}</p>
            )}
            <textarea
              aria-label={`Comentario de ${department.approver}`}
              placeholder="Comentario (obligatorio para rechazar o pedir cambios)"
              value={comments[department.department_id] ?? ""}
              onChange={(event) => setComments((current) => ({ ...current, [department.department_id]: event.target.value }))}
              rows={2}
              className="w-full rounded-md border border-slate-300 p-2 text-xs"
            />
            <div className="flex flex-wrap gap-2">
              {DECISIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  disabled={busy || !department.pending_interrupt || department.flags.arbitration_blocked}
                  onClick={() => decide(department, option.value)}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40 ${option.style}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            {!department.pending_interrupt && department.approval_status !== "aprobado" && (
              <p className="text-xs text-slate-500">Sin decisión pendiente en este momento.</p>
            )}
          </article>
        ))}
      </div>
      {snapshot.final_document && (
        <article className="space-y-2 rounded-md border border-emerald-300 bg-emerald-50 p-4">
          <h2 className="font-semibold">Documento final</h2>
          <p className="text-xs text-slate-600">
            {snapshot.final_document.currency ? `Moneda: ${snapshot.final_document.currency} · ` : ""}
            {snapshot.final_document.generated_at ?? ""}
          </p>
          <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded bg-white p-3 text-xs text-slate-800">
            {snapshot.final_document.content}
          </pre>
        </article>
      )}
    </div>
  );
}