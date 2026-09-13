import { NextResponse } from "next/server";

const BACKEND_BASE_URL =
  process.env.INVENTORY_API_INTERNAL_URL ??
  process.env.INCIDENTS_API_INTERNAL_URL ??
  "http://127.0.0.1:8000";

interface RouteParams {
  params: Promise<{ path: string[] }>;
}

function buildHeaders(request: Request): Record<string, string> {
  const headers: Record<string, string> = {};
  const authorization = request.headers.get("authorization");
  const contentType = request.headers.get("content-type");

  if (authorization) headers.authorization = authorization;
  if (contentType) headers["content-type"] = contentType;

  return headers;
}

async function proxyInventoryRequest(request: Request, path: string[]) {
  const normalizedPath = path[0] === "inventory" ? path.slice(1) : path;
  const targetUrl = `${BACKEND_BASE_URL}/inventory/${normalizedPath.map(encodeURIComponent).join("/")}`;
  const method = request.method;
  const body = method === "GET" || method === "HEAD" ? undefined : await request.text();

  try {
    const response = await fetch(targetUrl, {
      method,
      headers: buildHeaders(request),
      body,
    });
    const contentType = response.headers.get("content-type") ?? "application/json";
    const responseBody = await response.text();

    return new NextResponse(responseBody, {
      status: response.status,
      headers: { "content-type": contentType },
    });
  } catch {
    return NextResponse.json(
      { detail: "No se pudo conectar con el servicio de inventario. Verifica que la API este activa." },
      { status: 502 },
    );
  }
}

export async function GET(request: Request, context: RouteParams) {
  const { path } = await context.params;
  return proxyInventoryRequest(request, path);
}

export async function POST(request: Request, context: RouteParams) {
  const { path } = await context.params;
  return proxyInventoryRequest(request, path);
}