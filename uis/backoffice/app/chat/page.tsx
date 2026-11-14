"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { getToken, handleUnauthorized } from "@/lib/auth";

type ChatMessage = {
  message_id: string;
  role: "user" | "assistant";
  text: string;
  status: "completed" | "streaming" | "interrupted";
};
type ChatEvent = { event: string; data: Record<string, unknown> };

const SESSION_KEY = "trackflow_first_line_cx_session_id";
const WS_URL = process.env.NEXT_PUBLIC_AGENT_WS_URL || "ws://localhost:8000";

export default function ChatPage() {
  const [sessionId, setSessionId] = useState(() =>
    typeof window === "undefined" ? "" : localStorage.getItem(SESSION_KEY) || "",
  );
  const sessionIdRef = useRef(sessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(false);

  const connectRef = useRef<() => void>(() => undefined);
  const connect = useCallback(() => {
    const token = getToken();
    const activeSessionId = sessionIdRef.current;
    if (!token || !activeSessionId || !mountedRef.current) return;
    const socket = new WebSocket(`${WS_URL}/agent/chat/${activeSessionId}?token=${encodeURIComponent(token)}`);
    socketRef.current = socket;
    socket.onopen = () => {
      retryRef.current = 0;
      setConnected(true);
      setError("");
    };
    socket.onmessage = (message) => {
      let event: ChatEvent;
      try { event = JSON.parse(message.data) as ChatEvent; } catch { return; }
      const data = event.data || {};
      if (event.event === "session_snapshot" && Array.isArray(data.messages)) {
        setMessages(data.messages as ChatMessage[]);
      } else if (event.event === "user_message") {
        const userText = String(data.text || "");
        setMessages((current) => current.some((item) => item.role === "user" && item.text === userText)
          ? current
          : [...current, { message_id: `remote_${crypto.randomUUID()}`, role: "user", text: userText, status: "completed" }]);
      } else if (event.event === "token_chunk") {
        const messageId = String(data.message_id || "");
        const tokenText = String(data.token || "");
        setMessages((current) => {
          const index = current.findIndex((item) => item.message_id === messageId);
          if (index < 0) return [...current, {
            message_id: messageId, role: "assistant", text: tokenText, status: "streaming",
          }];
          return current.map((item) => item.message_id === messageId
            ? { ...item, text: item.text + tokenText, status: "streaming" }
            : item);
        });
      } else if (event.event === "generation_interrupted" || event.event === "generation_completed") {
        const messageId = String(data.message_id || "");
        setMessages((current) => current.map((item) => item.message_id === messageId
          ? { ...item, status: event.event === "generation_interrupted" ? "interrupted" : "completed" }
          : item));
      }
    };
    socket.onclose = (closeEvent) => {
      setConnected(false);
      if (closeEvent.code === 1008) {
        handleUnauthorized();
        setError("No se pudo autenticar el chat. Inicia sesión de nuevo.");
        return;
      }
      if (!mountedRef.current) return;
      const delay = Math.min(500 * (2 ** retryRef.current), 30000);
      retryRef.current += 1;
      timerRef.current = setTimeout(() => connectRef.current(), delay);
    };
    socket.onerror = () => socket.close();
  }, []);

  useEffect(() => {
    let id = sessionId;
    if (!id) {
      id = localStorage.getItem(SESSION_KEY) || crypto.randomUUID();
      localStorage.setItem(SESSION_KEY, id);
      sessionIdRef.current = id;
      queueMicrotask(() => setSessionId(id));
    }
    sessionIdRef.current = id;
    connectRef.current = connect;
    mountedRef.current = true;
    connectRef.current();
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      socketRef.current?.close();
    };
  // Mount once: resolving the ID asynchronously must not open a second socket.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = text.trim();
    const socket = socketRef.current;
    if (!normalized || !socket || socket.readyState !== WebSocket.OPEN || !sessionId) return;
    const streaming = messages.some((message) => message.role === "assistant" && message.status === "streaming");
    if (streaming) {
      socket.send(JSON.stringify({ event: "interrupt_requested", data: { session_id: sessionId, new_input: normalized } }));
    } else {
      socket.send(JSON.stringify({ event: "user_message", data: { session_id: sessionId, text: normalized } }));
    }
    setMessages((current) => [...current, {
      message_id: `local_${crypto.randomUUID()}`, role: "user", text: normalized, status: "completed",
    }]);
    setText("");
  }

  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto flex max-w-4xl flex-col px-4 py-8 sm:px-6 lg:px-8">
        <header className="border-b border-slate-300 pb-5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-teal-700">TrackFlow · Atención al cliente</p>
          <h1 className="mt-2 text-3xl font-extrabold text-slate-900">Chat con First-line CX</h1>
          <p className="mt-2 text-sm text-slate-600">Consulta sobre tracking, devoluciones o preguntas frecuentes. Puedes redirigir al agente mientras responde.</p>
          <p className="mt-2 text-xs" aria-live="polite">{connected ? "Conectado" : "Reconectando…"} · Sesión {sessionId ? sessionId.slice(0, 8) : "…"}</p>
        </header>
        <section className="mt-5 min-h-80 space-y-3" aria-live="polite" aria-label="Mensajes del chat">
          {messages.map((message) => (
            <article key={message.message_id} className={`max-w-[85%] rounded-xl px-4 py-3 ${message.role === "user" ? "ml-auto bg-teal-700 text-white" : "mr-auto border border-slate-200 bg-white text-slate-800"}`}>
              <p className="whitespace-pre-wrap text-sm">{message.text}</p>
              {message.status === "interrupted" && <p className="mt-2 text-xs font-semibold text-amber-700">Respuesta interrumpida · puedes continuar</p>}
              {message.status === "streaming" && <span className="sr-only">Respuesta en curso</span>}
            </article>
          ))}
        </section>
        {error && <p role="alert" className="mb-3 text-sm text-rose-700">{error}</p>}
        <form onSubmit={send} className="mt-5 flex items-end gap-3 border-t border-slate-300 pt-4">
          <label className="sr-only" htmlFor="chat-message">Tu mensaje</label>
          <textarea id="chat-message" value={text} onChange={(event) => setText(event.target.value)} maxLength={2000} rows={3} className="min-h-20 flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" placeholder="Escribe una consulta o redirige al agente…" />
          <button type="submit" disabled={!connected || !text.trim()} className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Enviar / interrumpir</button>
        </form>
      </section>
    </main>
  );
}
