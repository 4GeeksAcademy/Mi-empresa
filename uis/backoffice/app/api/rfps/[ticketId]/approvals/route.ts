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

export async function GET(request: Request, { params }: { params: Promise<{ ticketId: string }> }) {
  const { ticketId } = await params;
  try {
    const response = await backendFetch(request, `/api/rfps/${encodeURIComponent(ticketId)}/approvals`);
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Servicio de aprobaciones no disponible." }, { status: 502 });
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ ticketId: string }> }) {
  const { ticketId } = await params;
  try {
    const response = await backendFetch(request, `/api/rfps/${encodeURIComponent(ticketId)}/approvals`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Servicio de aprobaciones no disponible." }, { status: 502 });
  }
}