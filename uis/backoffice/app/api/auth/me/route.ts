import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
  try {
    const auth = request.headers.get("authorization");
    if (!auth) {
      return NextResponse.json({ detail: "No autorizado." }, { status: 401 });
    }

    const response = await fetch(`${BACKEND_BASE_URL}/auth/me`, {
      headers: { authorization: auth },
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "No se pudo conectar con el servicio de autenticación." },
      { status: 502 },
    );
  }
}