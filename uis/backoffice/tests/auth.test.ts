import { getToken, isTokenExpired, login, setToken, verifyToken } from "../lib/auth";

function jwtWithExpiry(exp: number): string {
  return `header.${btoa(JSON.stringify({ exp }))}.signature`;
}

function apiResponse(ok: boolean, body: object): Response {
  return { ok, json: jest.fn().mockResolvedValue(body) } as unknown as Response;
}

describe("helpers de autenticacion del backoffice", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.restoreAllMocks();
    global.fetch = jest.fn();
  });

  it("isTokenExpired acepta un JWT vigente y rechaza tokens malformados o expirados", () => {
    expect(isTokenExpired(jwtWithExpiry(Date.now() / 1000 + 60))).toBe(false);
    expect(isTokenExpired("not-a-jwt")).toBe(true);
    expect(isTokenExpired(jwtWithExpiry(Date.now() / 1000 - 60))).toBe(true);
  });

  it("verifyToken conserva tokens vigentes y elimina tokens vencidos", () => {
    setToken(jwtWithExpiry(Date.now() / 1000 + 60));
    expect(verifyToken()).toBe(true);
    expect(getToken()).not.toBeNull();

    setToken(jwtWithExpiry(Date.now() / 1000 - 60));
    expect(verifyToken()).toBe(false);
    expect(getToken()).toBeNull();
  });

  it("login devuelve el token emitido y propaga el detalle de un fallo de API", async () => {
    const fetchMock = global.fetch as jest.MockedFunction<typeof fetch>;
    fetchMock.mockResolvedValueOnce(apiResponse(true, { access_token: "access-token" }));

    await expect(login({ email: "agent@trackflow.com", password: "secure123" })).resolves.toBe("access-token");
    expect(fetchMock).toHaveBeenLastCalledWith("/api/auth/login", expect.objectContaining({ method: "POST" }));

    fetchMock.mockResolvedValueOnce(apiResponse(false, { detail: "Credenciales invalidas" }));
    await expect(login({ email: "agent@trackflow.com", password: "wrong" })).rejects.toThrow("Credenciales invalidas");
  });
});