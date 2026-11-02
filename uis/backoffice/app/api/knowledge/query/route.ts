import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/backend-fetch";

const BACKEND_BASE_URL = process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000";

export async function POST(request: Request) {
  try {
    const body: unknown = await request.json();
    const authorization = request.headers.get("authorization");
    const response = await backendFetch(request, `${BACKEND_BASE_URL}/knowledge/query`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(authorization ? { authorization } : {}),
      },
      body: JSON.stringify(body),
    });
    const responseBody = await response.text();
    return new NextResponse(responseBody, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "No se pudo conectar con la base de conocimiento." },
      { status: 502 },
    );
  }
}
