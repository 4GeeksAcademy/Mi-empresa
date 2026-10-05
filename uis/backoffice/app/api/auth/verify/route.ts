import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/backend-fetch";

const BACKEND_BASE_URL = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000";

export async function GET(request: Request) {
  try {
    const auth = request.headers.get("authorization");
    if (!auth) {
      return NextResponse.json({ valid: false }, { status: 401 });
    }

    const response = await backendFetch(request, `${BACKEND_BASE_URL}/auth/me`, {
      headers: { authorization: auth },
    });

    if (!response.ok) {
      return NextResponse.json({ valid: false }, { status: 401 });
    }

    const data = await response.json();
    return NextResponse.json({ valid: true, user: data });
  } catch {
    return NextResponse.json(
      { valid: false, detail: "No se pudo conectar con el servicio de autenticación." },
      { status: 502 },
    );
  }
}