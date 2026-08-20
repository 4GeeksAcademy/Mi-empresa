"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { forgotPassword } from "@/lib/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await forgotPassword(email);
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al procesar la solicitud.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell flex min-h-screen items-center justify-center p-6">
      <div className="card w-full max-w-sm p-8">
        <h1 className="text-2xl font-extrabold text-[var(--foreground)]">
          ¿Olvidaste tu contraseña?
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
          Introduce tu email y te enviaremos un enlace para restablecerla.
        </p>

        {submitted ? (
          <div
            className="mt-6 rounded-xl border px-4 py-4 text-sm font-medium"
            style={{
              borderColor: "rgb(22 163 74 / 0.2)",
              backgroundColor: "rgb(22 163 74 / 0.06)",
              color: "rgb(22 163 74)",
            }}
          >
            <p className="font-semibold">Enlace enviado</p>
            <p className="mt-1" style={{ color: "var(--muted)" }}>
              Si esa dirección está registrada, recibirás un enlace de
              restablecimiento en breve. Revisa tu bandeja de entrada y
              también la carpeta de spam.
            </p>
          </div>
        ) : (
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
                htmlFor="email"
                className="block text-sm font-semibold"
                style={{ color: "var(--foreground)" }}
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input mt-1"
                style={{ borderColor: "var(--border)" }}
                placeholder="usuario@ejemplo.com"
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
              {isLoading ? "Enviando enlace…" : "Enviar enlace de restablecimiento"}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-sm" style={{ color: "var(--muted)" }}>
          <Link
            href="/login"
            className="font-semibold"
            style={{ color: "var(--primary)" }}
          >
            Volver al inicio de sesión
          </Link>
        </p>
      </div>
    </main>
  );
}
