"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { register, setToken } from "@/lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    setIsLoading(true);

    try {
      const token = await register({
        email,
        password,
        name: name || undefined,
        phone: phone || undefined,
        address: address || undefined,
      });
      setToken(token);
      router.push("/");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Error al registrar.";
      if (message.toLowerCase().includes("email")) {
        setFieldErrors((prev) => ({ ...prev, email: message }));
      } else {
        setError(message);
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page-shell flex min-h-screen items-center justify-center p-6">
      <div className="card w-full max-w-sm p-8">
        <h1 className="text-2xl font-extrabold" style={{ color: "var(--foreground)" }}>Crear cuenta</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
          Regístrate para acceder al panel.
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
              Email <span style={{ color: "var(--danger)" }}>*</span>
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
            {fieldErrors.email && (
              <p className="mt-1 text-xs" style={{ color: "var(--danger)" }}>{fieldErrors.email}</p>
            )}
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-semibold" style={{ color: "var(--foreground)" }}>
              Contraseña <span style={{ color: "var(--danger)" }}>*</span>
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input mt-1"
              style={{ borderColor: "var(--border)" }}
              placeholder="Mínimo 6 caracteres"
            />
          </div>

          <hr className="border-t" style={{ borderColor: "var(--border)" }} />
          <p className="text-xs" style={{ color: "var(--muted)" }}>Campos opcionales de perfil</p>

          <div>
            <label htmlFor="name" className="block text-sm font-semibold" style={{ color: "var(--foreground)" }}>
              Nombre completo
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input mt-1"
              style={{ borderColor: "var(--border)" }}
              placeholder="Tu nombre"
            />
          </div>

          <div>
            <label htmlFor="phone" className="block text-sm font-semibold" style={{ color: "var(--foreground)" }}>
              Teléfono
            </label>
            <input
              id="phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="input mt-1"
              style={{ borderColor: "var(--border)" }}
              placeholder="+34 600 000 000"
            />
          </div>

          <div>
            <label htmlFor="address" className="block text-sm font-semibold" style={{ color: "var(--foreground)" }}>
              Dirección
            </label>
            <input
              id="address"
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="input mt-1"
              style={{ borderColor: "var(--border)" }}
              placeholder="Calle, ciudad, código postal"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition disabled:opacity-50"
            style={{ backgroundColor: "var(--primary)" }}
            onMouseOver={(e) => (e.currentTarget.style.backgroundColor = "var(--primary-strong)")}
            onMouseOut={(e) => (e.currentTarget.style.backgroundColor = "var(--primary)")}
          >
            {isLoading ? "Registrando…" : "Crear cuenta"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--muted)" }}>
          ¿Ya tienes cuenta?{" "}
          <Link
            href="/login"
            className="font-semibold"
            style={{ color: "var(--primary)" }}
          >
            Iniciar sesión
          </Link>
        </p>
      </div>
    </main>
  );
}