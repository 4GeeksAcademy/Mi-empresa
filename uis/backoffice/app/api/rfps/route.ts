import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/backend-fetch";

const BACKEND = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000";

export async function POST(request: Request) {
  try {
    const form = await request.formData();
    const response = await backendFetch(request, `${BACKEND}/api/rfps`, {
      method: "POST",
      headers: request.headers.get("authorization") ? { authorization: request.headers.get("authorization")! } : {},
      body: form,
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "No se pudo conectar con el servicio de RFP." }, { status: 502 });
  }
}