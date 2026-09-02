const AUTH_TOKEN_KEY = "auth_token";

// ─── Types ────────────────────────────────────────────────────────────

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterInput {
  email: string;
  password: string;
  role?: string;
  name?: string;
  phone?: string;
  address?: string;
}

export interface ProfileData {
  id: number;
  user_id: number;
  name: string | null;
  phone: string | null;
  address: string | null;
}

export interface AuthUser {
  id: number;
  email: string;
  role: string;
  profile: ProfileData | null;
}

// ─── Token helpers ────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function removeToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

/**
 * Decodifica el payload de un JWT y verifica si está expirado.
 * No requiere librerías externas, usa atob() del browser.
 */
export function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return true; // No es un JWT válido

    const payload = JSON.parse(atob(parts[1]));
    if (!payload || typeof payload.exp !== "number") return true;

    return Date.now() / 1000 >= payload.exp;
  } catch {
    return true; // Si no se puede decodificar, considerar expirado
  }
}

/**
 * Verifica si hay un token válido (existente y no expirado).
 * Si el token está expirado, lo limpia de localStorage.
 */
export function verifyToken(): boolean {
  const token = getToken();
  if (!token) return false;

  if (isTokenExpired(token)) {
    removeToken();
    return false;
  }

  return true;
}

// ─── Auth API calls ───────────────────────────────────────────────────

export async function login(input: LoginInput): Promise<string> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Error al iniciar sesión.");
  }

  const data = await response.json();
  return data.access_token;
}

export async function register(input: RegisterInput): Promise<string> {
  // 1. Crear usuario + auto-login via API Route proxy
  const response = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Error al registrar.");
  }

  const data = await response.json();
  return data.access_token;
}

export async function getMe(token: string): Promise<AuthUser> {
  const response = await fetch("/api/auth/me", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("No se pudo obtener la información del usuario.");
  }

  return response.json();
}

export async function updateProfile(
  token: string,
  data: { name?: string | null; phone?: string | null; address?: string | null },
): Promise<ProfileData> {
  const response = await fetch("/api/profiles/me", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Error al actualizar el perfil.");
  }

  return response.json();
}

export function logout(): void {
  removeToken();
  window.location.href = "/login";
}

export function handleUnauthorized(): void {
  removeToken();
  window.location.href = "/login";
}

// ── Password recovery and change ─────────────────────────────────────

export async function forgotPassword(email: string): Promise<void> {
  const response = await fetch("/api/auth/forgot-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Error al procesar la solicitud.");
  }
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<void> {
  const response = await fetch("/api/auth/reset-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Error al restablecer la contraseña.");
  }
}

export async function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const response = await fetch("/api/auth/change-password", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Error al cambiar la contraseña.");
  }
}