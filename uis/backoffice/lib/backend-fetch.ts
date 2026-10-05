export function backendFetch(request: Request, input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  for (const name of ["x-request-id", "x-session-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  return fetch(input, { ...init, headers });
}