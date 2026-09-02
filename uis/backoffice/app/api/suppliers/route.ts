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
    const url = new URL(request.url);
    const query = url.searchParams.toString();
    const targetUrl = query
      ? `${BACKEND_BASE_URL}/suppliers?${query}`
      : `${BACKEND_BASE_URL}/suppliers`;

    const response = await fetch(targetUrl, {
      method: "GET",
      headers: buildHeaders(request),
    });
    const contentType = response.headers.get("content-type") ?? "application/json";
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: { "content-type": contentType },
    });
  } catch {
    return NextResponse.json(
      {
        detail: "No se pudo conectar con el servicio de proveedores. Verifica que la API este activa.",
      },
      { status: 502 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const payload = await request.text();

    const response = await fetch(`${BACKEND_BASE_URL}/suppliers`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...buildHeaders(request),
      },
      body: payload,
    });

    const contentType = response.headers.get("content-type") ?? "application/json";
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: { "content-type": contentType },
    });
  } catch {
    return NextResponse.json(
      {
        detail: "No se pudo conectar con el servicio de proveedores. Verifica que la API este activa.",
      },
      { status: 502 },
    );
  }
}
