"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { verifyToken, getToken, getMe, updateProfile, logout, type AuthUser } from "@/lib/auth";

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    if (!verifyToken()) {
      router.push("/login");
      return;
    }

    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }

    getMe(token)
      .then((userData) => {
        if (!cancelled) {
          setName(userData.profile?.name ?? "");
          setPhone(userData.profile?.phone ?? "");
          setAddress(userData.profile?.address ?? "");
          setUser(userData);
        }
      })
      .catch(() => {
        if (!cancelled) setError("No se pudo cargar la información del perfil.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [router]);

  async function handleSave() {
    if (!verifyToken()) return;

    const token = getToken();
    if (!token) return;

    setSaving(true);
    setSaveMessage(null);
    setError(null);

    try {
      const updated = await updateProfile(token, {
        name: name || null,
        phone: phone || null,
        address: address || null,
      });
      setUser((prev) =>
        prev ? { ...prev, profile: updated } : prev,
      );
      setSaveMessage("Perfil actualizado correctamente.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al actualizar el perfil.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="page-shell flex min-h-screen items-center justify-center">
        <p style={{ color: "var(--muted)" }}>Cargando perfil…</p>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="page-shell flex min-h-screen items-center justify-center">
        <p style={{ color: "var(--danger)" }}>No se pudo cargar el perfil.</p>
      </main>
    );
  }

  return (
    <main className="page-shell min-h-screen">
      <section className="mx-auto max-w-2xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="card p-6">
          <h1 className="text-2xl font-extrabold" style={{ color: "var(--foreground)" }}>Mi perfil</h1>
          <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
            Gestiona tu información personal y de contacto.
          </p>

          {error && (
            <div
              className="mt-4 rounded-xl border px-4 py-3 text-sm font-medium"
              style={{
                borderColor: "rgb(180 35 24 / 0.2)",
                backgroundColor: "rgb(180 35 24 / 0.06)",
                color: "var(--danger)",
              }}
            >
              {error}
            </div>
          )}

          {saveMessage && (
            <div
              className="mt-4 rounded-xl border px-4 py-3 text-sm font-medium"
              style={{
                borderColor: "rgb(6 118 71 / 0.2)",
                backgroundColor: "rgb(6 118 71 / 0.06)",
                color: "var(--ok)",
              }}
            >
              {saveMessage}
            </div>
          )}

          <div className="mt-6 space-y-4">
            <div>
              <label className="block text-sm font-semibold" style={{ color: "var(--foreground)" }}>Email</label>
              <p
                className="mt-1 rounded-xl border px-3 py-2 text-sm"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-soft)", color: "var(--muted)" }}
              >
                {user.email}
              </p>
            </div>

            <div>
              <label className="block text-sm font-semibold" style={{ color: "var(--foreground)" }}>Rol</label>
              <p
                className="mt-1 rounded-xl border px-3 py-2 text-sm"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-soft)", color: "var(--muted)" }}
              >
                {user.role === "admin" ? "Administrador" : user.role === "manager" ? "Gestor" : "Usuario"}
              </p>
            </div>

            <hr className="border-t" style={{ borderColor: "var(--border)" }} />

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

            <div className="flex gap-3 pt-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded-xl px-4 py-2 text-sm font-semibold text-white transition disabled:opacity-50"
                style={{ backgroundColor: "var(--primary)" }}
                onMouseOver={(e) => (e.currentTarget.style.backgroundColor = "var(--primary-strong)")}
                onMouseOut={(e) => (e.currentTarget.style.backgroundColor = "var(--primary)")}
              >
                {saving ? "Guardando…" : "Guardar cambios"}
              </button>

              <button
                onClick={logout}
                className="rounded-xl border px-4 py-2 text-sm font-semibold transition"
                style={{ borderColor: "rgb(180 35 24 / 0.3)", color: "var(--danger)" }}
                onMouseOver={(e) => (e.currentTarget.style.backgroundColor = "rgb(180 35 24 / 0.06)")}
                onMouseOut={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
              >
                Cerrar sesión
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}