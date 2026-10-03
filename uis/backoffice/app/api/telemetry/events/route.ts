import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const response = await fetch(
      process.env.TELEMETRY_ENDPOINT ?? `${process.env.INCIDENTS_API_INTERNAL_URL ?? "http://backend:8000"}/telemetry/events`,
      {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload), signal: AbortSignal.timeout(5000),
      },
    );
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Telemetry receiver unavailable" }, { status: 502 });
  }
}