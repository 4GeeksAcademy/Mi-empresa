"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken, changePassword, logout } from "@/lib/auth";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Verificar autenticación al cargar
  const token = getToken();
  if (!token) {
    router.push("/login");
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError("No se encontró la sesión. Por favor, inicia sesión de nuevo.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Las contraseñas nuevas no coinciden.");
      return;
    }

    if (newPassword.length < 6) {
      setError("La nueva contraseña debe tener al menos 6 caracteres.");
      return;
    }

    setIsLoading(true);

    try {
      await changePassword(token, currentPassword, newPassword);
      setSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cambiar la contraseña.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleLogout() {
    logout();
  }

  return (
    <main className="page-shell flex min-h-screen items-center justify-center p-6">
      <div className="card w-full max-w-sm p-8">
        <h1 className="text-2xl font-extrabold text-[var(--foreground)]">
          Cambiar contraseña
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
          Actualiza tu contraseña para mantener tu cuenta segura.
        </p>

        {success && (
          <div
            className="mt-6 rounded-xl border px-4 py-3 text-sm font-medium"
            style={{
              borderColor: "rgb(22 163 74 / 0.2)",
              backgroundColor: "rgb(22 163 74 / 0.06)",
              color: "rgb(22 163 74)",
            }}
          >
            <p className="font-semibold">Contraseña actualizada</p>
            <p className="mt-1" style={{ color: "var(--muted)" }}>
              Tu contraseña ha sido cambiada correctamente. Por seguridad,
              te recomendamos cerrar sesión en otros dispositivos.
            </p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          {error && (
            <div
              className="rounded-xl border px-4 py-3 text-sm font-medium"
              style={{
                borderColor: "rgb(180 35 24 / 0.2)",
                backgroundColor: "rgb(180 35 24 / 0.06)",
                color: "var(--danger)",
              }}
            >
              {error}
            </div>
          )}

          <div>
            <label
              htmlFor="currentPassword"
              className="block text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              Contraseña actual
            </label>
            <input
              id="currentPassword"
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="input mt-1"
              style={{ borderColor: "var(--border)" }}
              placeholder="••••••••"
            />
          </div>

          <div>
            <label
              htmlFor="newPassword"
              className="block text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              Nueva contraseña
            </label>
            <input
              id="newPassword"
              type="password"
              required
              minLength={6}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="input mt-1"
              style={{ borderColor: "var(--border)" }}
              placeholder="••••••••"
            />
          </div>

          <div>
            <label
              htmlFor="confirmPassword"
              className="block text-sm font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              Confirmar nueva contraseña
            </label>
            <input
              id="confirmPassword"
              type="password"
              required
              minLength={6}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="input mt-1"
              style={{ borderColor: "var(--border)" }}
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition disabled:opacity-50"
            style={{
              backgroundColor: "var(--primary)",
            }}
            onMouseOver={(e) =>
              (e.currentTarget.style.backgroundColor = "var(--primary-strong)")
            }
            onMouseOut={(e) =>
              (e.currentTarget.style.backgroundColor = "var(--primary)")
            }
          >
            {isLoading ? "Cambiando contraseña…" : "Cambiar contraseña"}
          </button>
        </form>

        <div className="mt-6 flex flex-col gap-2 text-center text-sm" style={{ color: "var(--muted)" }}>
          <Link
            href="/account/profile"
            className="font-semibold"
            style={{ color: "var(--primary)" }}
          >
            Volver al perfil
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="font-semibold"
            style={{ color: "var(--danger)" }}
          >
            Cerrar sesión
          </button>
        </div>
      </div>
    </main>
  );
}
