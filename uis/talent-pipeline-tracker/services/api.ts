import { ApiErrorResponse } from "@/types/candidates";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_TRACKER_API_BASE_URL ?? "https://playground.4geeks.com/tracker/api/v1";

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let errorMessage = `Error ${response.status}`;
    try {
      const payload = (await response.json()) as ApiErrorResponse;
      if (payload.error) {
        errorMessage = payload.error;
      } else if (typeof payload.detail === "string") {
        errorMessage = payload.detail;
      } else if (Array.isArray(payload.detail) && payload.detail.length > 0) {
        errorMessage = payload.detail[0].msg ?? errorMessage;
      }
    } catch {
      // Ignorar parseo fallido y usar mensaje por defecto.
    }
    throw new Error(errorMessage);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
