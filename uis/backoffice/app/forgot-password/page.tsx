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
    <main className="ops-bg flex min-h-screen items-center justify-center">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-extrabold text-slate-900">
          ¿Olvidaste tu contraseña?
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Introduce tu email y te enviaremos un enlace para restablecerla.
        </p>

        {submitted ? (
          <div className="mt-6 rounded-xl border border-green-200 bg-green-50 px-4 py-4 text-sm font-medium text-green-700">
            <p className="font-semibold">Enlace enviado</p>
            <p className="mt-1 text-slate-600">
              Si esa dirección está registrada, recibirás un enlace de
              restablecimiento en breve. Revisa tu bandeja de entrada y
              también la carpeta de spam.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            {error && (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                {error}
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-sm font-semibold text-slate-700">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
                placeholder="usuario@ejemplo.com"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:opacity-50"
            >
              {isLoading ? "Enviando enlace…" : "Enviar enlace de restablecimiento"}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-slate-600">
          <Link href="/login" className="font-semibold text-teal-700 hover:text-teal-800">
            Volver al inicio de sesión
          </Link>
        </p>
      </div>
    </main>
  );
}
