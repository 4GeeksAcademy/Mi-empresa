import { NextResponse } from "next/server";

const BACKEND = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000";

async function backendFetch(request: Request, path: string) {
  return fetch(`${BACKEND}${path}`, {
    headers: {
      authorization: request.headers.get("authorization") ?? "",
    },
    cache: "no-store",
  });
}

export async function GET(request: Request, { params }: { params: Promise<{ ticketId: string }> }) {
  const { ticketId } = await params;
  try {
    const response = await backendFetch(request, `/api/rfps/${encodeURIComponent(ticketId)}/final-document`);
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Documento final no disponible." }, { status: 502 });
  }
}