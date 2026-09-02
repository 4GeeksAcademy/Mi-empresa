import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const response = await fetch(`${BACKEND_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
