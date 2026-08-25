import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: Request, { params }: RouteParams) {
  try {
    const { id } = await params;
    const payload = await request.text();

    const response = await fetch(`${BACKEND_BASE_URL}/suppliers/${id}/rate`, {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
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
