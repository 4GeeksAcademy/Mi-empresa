import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/backend-fetch";

const BACKEND = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000";

export async function GET(request: Request) {
  try {
    const url = new URL(`${BACKEND}/api/rfps`);
    const createdAfter = new URL(request.url).searchParams.get("created_after");
    if (createdAfter) url.searchParams.set("created_after", createdAfter);
    const response = await backendFetch(request, url, {
      headers: request.headers.get("authorization") ? { authorization: request.headers.get("authorization")! } : {},
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "No se pudo conectar con el servicio de RFP." }, { status: 502 });
  }
}

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