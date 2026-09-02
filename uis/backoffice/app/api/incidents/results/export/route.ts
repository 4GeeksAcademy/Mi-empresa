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

export async function GET(request: Request) {
  try {
    const authHeader = request.headers.get("authorization");

    const headers: Record<string, string> = {};
    if (authHeader) {
      headers["Authorization"] = authHeader;
    }

    const response = await fetch(`${BACKEND_BASE_URL}/api/incidents/results/export`, {
      method: "GET",
      headers,
      headers: buildHeaders(request),
    });

    const contentType = response.headers.get("content-type") ?? "text/csv; charset=utf-8";
    const contentDisposition =
      response.headers.get("content-disposition") ??
      "attachment; filename=results.csv";
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type": contentType,
        "content-disposition": contentDisposition,
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
