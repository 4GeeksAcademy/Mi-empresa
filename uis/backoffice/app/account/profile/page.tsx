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
    if (!token) {
      router.push("/login");
      return;
    }

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
    } catch {
      // Token inválido o expirado → limpiar y redirigir al login
      localStorage.removeItem("auth_token");
      router.push("/login");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="ops-bg flex min-h-screen items-center justify-center">
        <p className="text-sm text-slate-600">Cargando perfil…</p>
      </main>
    );
  }

  if (!user) {
    // No debería llegar aquí porque loadProfile ya redirige,
    // pero por seguridad, redirigir al login
    router.push("/login");
    return null;
  }

  return (
    <main className="ops-bg min-h-screen">
      <section className="mx-auto max-w-2xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-extrabold text-slate-900">Mi perfil</h1>
          <p className="mt-1 text-sm text-slate-600">
            Gestiona tu información personal y de contacto.
          </p>

          {error && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
              {error}
            </div>
          )}

          {saveMessage && (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
              {saveMessage}
            </div>
          )}

          <div className="mt-6 space-y-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700">Email</label>
              <p className="mt-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                {user.email}
              </p>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700">Rol</label>
              <p className="mt-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                {user.role === "admin" ? "Administrador" : user.role === "manager" ? "Gestor" : "Usuario"}
              </p>
            </div>

            <hr className="border-slate-200" />

            <div>
              <label htmlFor="name" className="block text-sm font-semibold text-slate-700">
                Nombre completo
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
                placeholder="Tu nombre"
              />
            </div>

            <div>
              <label htmlFor="phone" className="block text-sm font-semibold text-slate-700">
                Teléfono
              </label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
                placeholder="+34 600 000 000"
              />
            </div>

            <div>
              <label htmlFor="address" className="block text-sm font-semibold text-slate-700">
                Dirección
              </label>
              <input
                id="address"
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
                placeholder="Calle, ciudad, código postal"
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:opacity-50"
              >
                {saving ? "Guardando…" : "Guardar cambios"}
              </button>

              <button
                onClick={logout}
                className="rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-50"
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