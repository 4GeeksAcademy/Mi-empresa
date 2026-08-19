import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

interface RouteParams {
  params: Promise<{ id: string }>;
}

function buildHeaders(request: Request): Record<string, string> {
  const headers: Record<string, string> = {};
  const auth = request.headers.get("authorization");
  if (auth) {
    headers["authorization"] = auth;
  }
  return headers;
}

export async function GET(request: Request, { params }: RouteParams) {
  try {
    const { id } = await params;

    const response = await fetch(`${BACKEND_BASE_URL}/suppliers/${id}`, {
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

export async function DELETE(request: Request, { params }: RouteParams) {
  try {
    const { id } = await params;

    const response = await fetch(`${BACKEND_BASE_URL}/suppliers/${id}`, {
      method: "DELETE",
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
