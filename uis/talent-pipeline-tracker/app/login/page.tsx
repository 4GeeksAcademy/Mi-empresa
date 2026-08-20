"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { login, setToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const token = await login({ email, password });
      setToken(token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al iniciar sesión.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell flex min-h-screen items-center justify-center p-6">
      <div className="card w-full max-w-sm p-8">
        <h1 className="text-2xl font-extrabold text-[var(--foreground)]">Iniciar sesión</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
          Accede al panel de Talent Pipeline.
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
            <label htmlFor="email" className="block text-sm font-semibold" style={{ color: "var(--foreground)" }}>
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

          <div>
            <label htmlFor="password" className="block text-sm font-semibold" style={{ color: "var(--foreground)" }}>
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input mt-1"
              style={{ borderColor: "var(--border)" }}
              placeholder="••••••••"
            />
          </div>

          <div className="text-right">
            <Link
              href="/forgot-password"
              className="text-xs font-semibold"
              style={{ color: "var(--primary)" }}
            >
              ¿Olvidaste tu contraseña?
            </Link>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition disabled:opacity-50"
            style={{
              backgroundColor: "var(--primary)",
            }}
            onMouseOver={(e) => (e.currentTarget.style.backgroundColor = "var(--primary-strong)")}
            onMouseOut={(e) => (e.currentTarget.style.backgroundColor = "var(--primary)")}
          >
            {isLoading ? "Iniciando sesión…" : "Iniciar sesión"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--muted)" }}>
          ¿No tienes cuenta?{" "}
          <Link
            href="/register"
            className="font-semibold"
            style={{ color: "var(--primary)" }}
          >
            Registrarse
          </Link>
        </p>
      </div>
    </main>
  );
}