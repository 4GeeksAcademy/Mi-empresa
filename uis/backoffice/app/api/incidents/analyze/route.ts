import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

function buildHeaders(request: Request): Record<string, string> {
  const headers: Record<string, string> = {};
  const auth = request.headers.get("authorization");
  if (auth) {
    headers["authorization"] = auth;
  }
  return headers;
}

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const authHeader = request.headers.get("authorization");

    const headers: Record<string, string> = {};
    if (authHeader) {
      headers["Authorization"] = authHeader;
    }

    const response = await fetch(`${BACKEND_BASE_URL}/api/incidents/analyze`, {
      method: "POST",
      headers: buildHeaders(request),
      body: formData,
    });

    const contentType = response.headers.get("content-type") ?? "application/json";
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type": contentType,
      },
    });
  } catch {
    return NextResponse.json(
      {
        detail: "No se pudo conectar con el servicio de analisis. Verifica que la API este activa.",
      },
      { status: 502 },
    );
  }
}
