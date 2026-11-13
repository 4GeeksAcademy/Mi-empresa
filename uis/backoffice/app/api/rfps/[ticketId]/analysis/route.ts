import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/backend-fetch";

const BACKEND = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000";

export async function GET(request: Request, context: { params: Promise<{ ticketId: string }> }) {
  try {
    const { ticketId } = await context.params;
    const response = await backendFetch(request, `${BACKEND}/api/rfps/${encodeURIComponent(ticketId)}/analysis`, {
      headers: request.headers.get("authorization") ? { authorization: request.headers.get("authorization")! } : {},
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "No se pudo conectar con el servicio de RFP." }, { status: 502 });
  }
}