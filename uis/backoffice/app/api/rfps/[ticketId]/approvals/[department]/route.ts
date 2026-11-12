import { NextResponse } from "next/server";

const BACKEND = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000";

async function backendFetch(request: Request, path: string, init?: RequestInit) {
  return fetch(`${BACKEND}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: request.headers.get("authorization") ?? "",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
}

// Registro de la decisión de un responsable: aprueba/rechaza una sección sin
// releer el documento completo. El backend valida aprobador, comentario e
// interrupt pendiente antes de reinsertar la respuesta en el grafo.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ ticketId: string; department: string }> },
) {
  const { ticketId, department } = await params;
  try {
    const payload = await request.json().catch(() => null);
    const response = await backendFetch(
      request,
      `/api/rfps/${encodeURIComponent(ticketId)}/approvals/${encodeURIComponent(department)}`,
      { method: "POST", body: JSON.stringify(payload ?? {}) },
    );
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Servicio de aprobaciones no disponible." }, { status: 502 });
  }
}