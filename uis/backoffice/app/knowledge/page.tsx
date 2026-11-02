"use client";

import { FormEvent, useState } from "react";
import { getToken, handleUnauthorized } from "@/lib/auth";

type KnowledgeResponse = { answer: string };

export default function KnowledgePage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion || isLoading) return;

    setIsLoading(true);
    setError("");
    setAnswer("");
    try {
      const token = getToken();
      const response = await fetch("/api/knowledge/query", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(token ? { authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question: normalizedQuestion }),
      });
      if (response.status === 401) {
        handleUnauthorized();
        throw new Error("Tu sesión ha caducado. Inicia sesión de nuevo.");
      }
      if (!response.ok) {
        throw new Error(response.status >= 500
          ? "El asistente no está disponible ahora. Inténtalo más tarde."
          : "No se pudo procesar la pregunta. Revisa el texto e inténtalo de nuevo.");
      }
      const result = (await response.json()) as KnowledgeResponse;
      if (!result.answer?.trim()) throw new Error("El asistente no devolvió una respuesta.");
      setAnswer(result.answer);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo enviar la pregunta.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="border-b border-slate-300 pb-5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-teal-700">TrackFlow · Comercial</p>
          <h1 className="mt-2 text-3xl font-extrabold text-slate-900">Base de conocimiento</h1>
          <p className="mt-2 text-sm text-slate-600">Consulta condiciones estándar de entrega, devoluciones, transportistas y almacenamiento.</p>
        </header>

        <form onSubmit={handleSubmit} className="mt-6 grid gap-3">
          <label htmlFor="knowledge-question" className="text-sm font-semibold text-slate-700">Pregunta para el asistente</label>
          <textarea
            id="knowledge-question"
            className="min-h-32 rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:border-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-700/20"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={2000}
            placeholder="Ej.: ¿Cuál es la ventana de devolución estándar?"
            required
            disabled={isLoading}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-slate-500">El asistente responde según la documentación estándar; confirma las condiciones específicas del contrato.</p>
            <button
              className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
              type="submit"
              disabled={isLoading || !question.trim()}
            >
              {isLoading ? "Consultando…" : "Consultar"}
            </button>
          </div>
        </form>

        {isLoading && <p className="mt-6 text-sm text-slate-600" aria-live="polite">Buscando en la base de conocimiento y preparando la respuesta…</p>}
        {error && <p role="alert" className="mt-6 border-l-4 border-rose-600 bg-rose-50 px-4 py-3 text-sm text-rose-900">{error}</p>}
        {answer && (
          <section className="mt-6 border border-slate-200 bg-white p-5" aria-live="polite" aria-labelledby="knowledge-answer-heading">
            <h2 id="knowledge-answer-heading" className="text-lg font-bold text-slate-900">Respuesta</h2>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700">{answer}</p>
          </section>
        )}
      </section>
    </main>
  );
}
