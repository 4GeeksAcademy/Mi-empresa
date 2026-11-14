import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/backend-fetch";

const BACKEND = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000";

export async function GET(request: Request) {
  try {
    const authorization = request.headers.get("authorization");
    if (!authorization) return NextResponse.json({ detail: "Autenticación requerida." }, { status: 401 });
    const url = new URL(`${BACKEND}/api/rfps/events`);
    const since = new URL(request.url).searchParams.get("since");
    if (since) url.searchParams.set("since", since);
    const response = await backendFetch(request, url, { headers: { authorization } });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "text/event-stream",
        "cache-control": "no-cache, no-transform",
        "x-accel-buffering": "no",
      },
    });
  } catch {
    return NextResponse.json({ detail: "No se pudo conectar con el servicio de RFP." }, { status: 502 });
  }
}