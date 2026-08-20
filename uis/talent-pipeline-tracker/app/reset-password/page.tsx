"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";
import { resetPassword } from "@/lib/auth";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!token) {
    return (
      <main className="page-shell flex min-h-screen items-center justify-center p-6">
        <div className="card w-full max-w-sm p-8">
          <h1 className="text-2xl font-extrabold text-[var(--foreground)]">
            Enlace no válido
          </h1>
          <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
            No se encontró un token de restablecimiento en la URL. Solicita un
            nuevo enlace.
          </p>
          <Link
            href="/forgot-password"
            className="mt-4 inline-block font-semibold text-sm"
            style={{ color: "var(--primary)" }}
          >
            Solicitar nuevo enlace
          </Link>
        </div>
      </main>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError("Token no encontrado. Solicita un nuevo enlace.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    if (newPassword.length < 6) {
      setError("La contraseña debe tener al menos 6 caracteres.");
      return;
    }

    setIsLoading(true);

    try {
      await resetPassword(token, newPassword);
      router.push("/login?reset=success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al restablecer la contraseña.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell flex min-h-screen items-center justify-center p-6">
      <div className="card w-full max-w-sm p-8">
        <h1 className="text-2xl font-extrabold text-[var(--foreground)]">
          Nueva contraseña
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
          Introduce tu nueva contraseña a continuación.
        </p>

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
              Confirmar contraseña
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
            {isLoading ? "Restableciendo…" : "Restablecer contraseña"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--muted)" }}>
          <Link
            href="/forgot-password"
            className="font-semibold"
            style={{ color: "var(--primary)" }}
          >
            Solicitar un nuevo enlace
          </Link>
        </p>
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <main className="page-shell flex min-h-screen items-center justify-center p-6">
          <div className="card w-full max-w-sm p-8 text-center">
            <p style={{ color: "var(--muted)" }}>Cargando…</p>
          </div>
        </main>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
