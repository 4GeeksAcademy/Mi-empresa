import { telemetry } from "./telemetry";
import { getToken } from "./auth";

export function correlatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(typeof Request !== "undefined" && input instanceof Request ? input.headers : undefined);
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  const token = getToken();
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  Object.entries(telemetry.correlationHeaders()).forEach(([key, value]) => headers.set(key, value));
  return fetch(input, { ...init, headers });
}