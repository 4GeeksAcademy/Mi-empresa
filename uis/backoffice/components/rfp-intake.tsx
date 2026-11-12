"use client";

import { FormEvent, useEffect, useState } from "react";

import { RfpApprovals } from "./rfp-approvals";

type Ticket = {
  ticket_id: string;
  status: string;
  filename: string;
  processing_error: string | null;
  classification: { is_rfp: boolean | null; reason: string | null };
  metadata: null | {
    client_name: string | null;
    client_country: string | null;
    monthly_volume: number | null;
    currency: string | null;
    departments_needed: string[];
    readability_metrics: Record<string, number | boolean>;
  };
  department_sections: Array<{ department_id: string; approver: string; key_aspects: string[]; open_questions: string[] }>;
  handoff: unknown;
};

export function RfpIntake() {
  const [file, setFile] = useState<File | null>(null);
  const [ticketId, setTicketId] = useState("");
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!ticketId || ticket?.status !== "analizando" || ticket.processing_error) return;
    const timer = window.setInterval(async () => {
      const response = await fetch(`/api/rfps/${encodeURIComponent(ticketId)}`);
      if (!response.ok) return;
      const result = (await response.json()) as Ticket;
      setTicket(result);
      if (result.status !== "analizando" || result.processing_error) window.clearInterval(timer);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [ticketId, ticket?.status, ticket?.processing_error]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!file) return setError("Selecciona un PDF para continuar.");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/rfps", { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : result.detail?.message ?? "No se pudo cargar la RFP.");
      setTicketId(result.ticket_id);
      setTicket({ ticket_id: result.ticket_id, status: result.status, filename: file.name, processing_error: null,
        classification: { is_rfp: null, reason: null }, metadata: null, department_sections: [], handoff: null });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo procesar la solicitud.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div><h1 className="text-2xl font-semibold text-slate-900">Recepción de RFPs</h1>
        <p className="mt-2 text-sm text-slate-600">Carga un PDF. Se convertirá a Markdown antes de clasificarlo y enrutarlo.</p></div>
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input aria-label="PDF de RFP" type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="block w-full text-sm" />
        <button disabled={busy} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Enviando…" : "Analizar PDF"}</button>
      </form>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {ticket && <div aria-live="polite" className="space-y-4 border-t border-slate-200 pt-4">
        <p className="text-sm"><strong>Ticket:</strong> {ticket.ticket_id} · <strong>Estado:</strong> {ticket.status} · {ticket.filename}</p>
        {ticket.processing_error && <p role="alert" className="text-sm text-red-700">{ticket.processing_error}</p>}
        {ticket.status !== "analizando" && <p className="text-sm">{ticket.classification.is_rfp ? "RFP aceptada" : "Documento descartado"} · {ticket.classification.reason}</p>}
        {ticket.classification.is_rfp && ticket.status !== "analizando" && ticket.status !== "analisis_completo" && ticket.status !== "generando_borrador" && (
          <RfpApprovals ticketId={ticket.ticket_id} status={ticket.status} />
        )}
        {ticket.metadata && <div className="space-y-2 text-sm">
          <h2 className="font-semibold">Datos extraídos</h2>
          <p>Cliente: {ticket.metadata.client_name ?? "No identificado"} · País: {ticket.metadata.client_country ?? "No identificado"} · Volumen mensual: {ticket.metadata.monthly_volume ?? "No indicado"} · Moneda: {ticket.metadata.currency ?? "No determinada"}</p>
          <p>Departamentos: {ticket.metadata.departments_needed.join(", ") || "Ninguno"}</p>
          <h2 className="pt-2 font-semibold">Aspectos y preguntas para responsables</h2>
          {ticket.department_sections.map((section) => <article key={section.department_id} className="rounded-md bg-slate-50 p-3">
            <h3 className="font-semibold">{section.department_id} — {section.approver}</h3>
            <ul className="list-disc pl-5">{section.key_aspects.map((aspect, index) => <li key={`${section.department_id}-a-${index}`}>{aspect}</li>)}</ul>
            {section.open_questions.length > 0 && <p className="mt-2">Preguntas abiertas: {section.open_questions.join("; ")}</p>}
          </article>)}
        </div>}
      </div>}
    </section>
  );
}