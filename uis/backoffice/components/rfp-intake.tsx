"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { getToken } from "@/lib/auth";
import { RfpApprovals } from "./rfp-approvals";

type Ticket = {
  ticket_id: string;
  rfp_id: string;
  created_at: string;
  accepted_at: string | null;
  status: string;
  filename: string;
  processing_error: string | null;
  classification: { is_rfp: boolean | null; reason: string | null };
  metadata: null | {
    client_name: string | null;
    client_country: string | null;
    services_requested: string[];
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
  const [arrivals, setArrivals] = useState<Array<{ ticket_id: string; rfp_id: string; client_name: string | null; client_country: string | null; services_requested: string[]; status: string; created_at: string }>>([]);
  const seenIds = useRef(new Set<string>());

  const addArrival = useCallback((arrival: (typeof arrivals)[number]) => {
    if (seenIds.current.has(arrival.ticket_id)) return;
    seenIds.current.add(arrival.ticket_id);
    setArrivals((current) => [arrival, ...current]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let activeController: AbortController | null = null;
    let retryTimer: number | undefined;
    let failures = 0;
    const pageOpenedAt = new Date().toISOString();

    async function connect() {
      const token = getToken();
      if (!token || cancelled) return;
      activeController = new AbortController();
      try {
        // Recovery: merge the authoritative recent-ticket snapshot on every
        // (re)connect before opening the live stream. ticket_id deduplicates overlap.
        const snapshot = await fetch(`/api/rfps?created_after=${encodeURIComponent(pageOpenedAt)}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: activeController.signal,
        });
        if (!snapshot.ok) throw new Error("No se pudo recuperar la lista de RFPs.");
        const tickets = (await snapshot.json()) as Ticket[];
        if (cancelled) return;
        for (const item of tickets) {
          if (item.accepted_at && new Date(item.accepted_at) >= new Date(pageOpenedAt)) {
            addArrival({ ticket_id: item.ticket_id, rfp_id: item.rfp_id, client_name: item.metadata?.client_name ?? null,
              client_country: item.metadata?.client_country ?? null, services_requested: item.metadata?.services_requested ?? [], status: "analyzing",
              created_at: item.accepted_at });
          }
        }

        const response = await fetch(`/api/rfps/events?since=${encodeURIComponent(pageOpenedAt)}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: activeController.signal,
        });
        if (!response.ok || !response.body) throw new Error("El stream SSE no está disponible.");
        const connectedAt = Date.now();
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!cancelled) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const frame = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            let eventName = "";
            let data = "";
            for (const line of frame.split(/\r?\n/)) {
              if (line.startsWith("event:")) eventName = line.slice(6).trim();
              if (line.startsWith("data:")) data += line.slice(5).trim();
            }
            if (eventName === "rfp_ticket_created" && data) {
              addArrival(JSON.parse(data) as (typeof arrivals)[number]);
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
        if (Date.now() - connectedAt >= 60_000) failures = 0;
        if (!cancelled) throw new Error("El stream SSE se interrumpió.");
      } catch {
        if (cancelled || activeController?.signal.aborted) return;
        failures += 1;
        const delay = Math.min(30_000, 500 * 2 ** Math.min(failures - 1, 6));
        retryTimer = window.setTimeout(() => void connect(), delay);
      }
    }

    void connect();
    return () => {
      cancelled = true;
      activeController?.abort();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [addArrival]);

  useEffect(() => {
    if (!ticketId || ticket?.status !== "analizando" || ticket.processing_error) return;
    const timer = window.setInterval(async () => {
      const token = getToken();
      const response = await fetch(`/api/rfps/${encodeURIComponent(ticketId)}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
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
      const token = getToken();
      const response = await fetch("/api/rfps", { method: "POST", body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {} });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : result.detail?.message ?? "No se pudo cargar la RFP.");
      setTicketId(result.ticket_id);
      setTicket({ ticket_id: result.ticket_id, rfp_id: result.rfp_id, created_at: new Date().toISOString(), accepted_at: null,
        status: result.status, filename: file.name, processing_error: null,
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
      <aside aria-live="polite" aria-label="Nuevas RFP" className="rounded-lg border border-amber-300 bg-amber-50 p-4">
        <h2 className="font-semibold text-amber-950">Llegadas de RFP en tiempo real</h2>
        {arrivals.length === 0 ? <p className="mt-1 text-sm text-amber-900">Esperando nuevos tickets…</p> :
          <ul className="mt-2 space-y-2">{arrivals.map((arrival) => <li key={arrival.ticket_id} className="rounded-md bg-white p-3 text-sm shadow-sm">
            <strong>Nueva RFP · requiere procesamiento</strong><br />
            Ticket {arrival.ticket_id} · {arrival.client_name ?? "Cliente por identificar"} · {arrival.client_country ?? "País por identificar"} · {new Date(arrival.created_at).toLocaleString()}
          </li>)}</ul>}
      </aside>
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