"use client";

import { FormEvent, useState } from "react";

interface IncidentFieldError {
  field: string;
  message: string;
}

const CATEGORIES = [
  { value: "logistica", label: "Logistica" },
  { value: "tracking", label: "Tracking" },
  { value: "devolucion", label: "Devolucion" },
  { value: "facturacion", label: "Facturacion" },
  { value: "soporte", label: "Soporte" },
];

const ORIGINS = [
  { value: "customer", label: "Cliente" },
  { value: "branch", label: "Sede" },
  { value: "internal", label: "Interno" },
];

const BRANCHES = [
  { value: "los-angeles", label: "Los Angeles" },
  { value: "zaragoza", label: "Zaragoza" },
  { value: "central", label: "Central" },
];

const STATUSES = [
  { value: "open", label: "Abierta" },
  { value: "in_progress", label: "En progreso" },
  { value: "resolved", label: "Resuelta" },
  { value: "discarded", label: "Descartada" },
];

function parseErrors(errorBody: unknown): IncidentFieldError[] {
  if (typeof errorBody !== "object" || errorBody === null) {
    return [{ field: "general", message: "Error inesperado en la solicitud." }];
  }

  const body = errorBody as Record<string, unknown>;

  // Si es un error de validacion con campo identificado
  if (body.field && typeof body.field === "string" && body.message && typeof body.message === "string") {
    return [{ field: body.field, message: body.message }];
  }

  // Si es un error de detalle general (HTTPException de FastAPI)
  if (body.detail && typeof body.detail === "string") {
    // Intentar extraer campo del mensaje de error
    const detail = body.detail;
    const fieldMatch = detail.match(/(?:el|la) '(\w+)'/i);
    if (fieldMatch) {
      return [{ field: fieldMatch[1], message: detail }];
    }
    return [{ field: "general", message: detail }];
  }

  // Errores de validacion Pydantic (lista de errores)
  if (Array.isArray(body.detail)) {
    return body.detail.map((err: unknown) => {
      if (typeof err === "object" && err !== null) {
        const e = err as Record<string, unknown>;
        const loc = Array.isArray(e.loc) ? e.loc.slice(1).join(".") : "general";
        return {
          field: loc,
          message: typeof e.msg === "string" ? e.msg : "Dato invalido.",
        };
      }
      return { field: "general", message: "Error de validacion." };
    });
  }

  return [{ field: "general", message: "No se pudo enviar la incidencia." }];
}

export function IncidentForm() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("open");
  const [origin, setOrigin] = useState("customer");
  const [branch, setBranch] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function resetForm() {
    setTitle("");
    setDescription("");
    setCategory("");
    setStatus("open");
    setOrigin("customer");
    setBranch("");
    setFieldErrors({});
    setGeneralError(null);
  }

  function validateClient(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!title.trim()) errors.title = "El titulo es obligatorio.";
    if (!description.trim()) errors.description = "La descripcion es obligatoria.";
    if (!category) errors.category = "Selecciona una categoria.";
    if (!origin) errors.origin = "Selecciona un origen.";
    if (!branch) errors.branch = "Selecciona una sede.";
    return errors;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldErrors({});
    setGeneralError(null);
    setSuccessMessage(null);

    // Validacion en cliente
    const clientErrors = validateClient();
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch("/api/incidents", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
          category,
          status,
          origin,
          branch,
        }),
      });

      if (!response.ok) {
        const errorBody = await response.json() as unknown;
        const errors = parseErrors(errorBody);
        const fieldMap: Record<string, string> = {};
        for (const err of errors) {
          if (err.field !== "general") {
            fieldMap[err.field] = err.message;
          } else {
            setGeneralError(err.message);
          }
        }
        if (Object.keys(fieldMap).length > 0) {
          setFieldErrors(fieldMap);
        }
        if (errors.length === 0) {
          setGeneralError("No se pudo registrar la incidencia. Intentalo de nuevo.");
        }
        return;
      }

      // Exito
      resetForm();
      setSuccessMessage("Incidencia registrada correctamente.");
    } catch {
      setGeneralError("No se pudo conectar con el servidor. Verifica la conexion e intentalo de nuevo.");
    } finally {
      setIsLoading(false);
    }
  }

  const isBranchHighlighted = origin === "branch";

  return (
    <section className="space-y-6">
      <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-extrabold text-slate-900">Nueva incidencia</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Registra una nueva incidencia en el sistema. Todos los campos marcados con * son obligatorios.
        </p>

        {successMessage && (
          <div className="mt-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">
            {successMessage}
          </div>
        )}

        {generalError && (
          <div className="mt-4 rounded-lg bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-800">
            {generalError}
          </div>
        )}

        <form className="mt-6 space-y-5" onSubmit={onSubmit}>
          {/* Titulo */}
          <div>
            <label htmlFor="title" className="block text-sm font-semibold text-slate-700">
              Titulo *
            </label>
            <input
              id="title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={`mt-1 block w-full rounded-lg border px-3 py-2 text-sm shadow-sm transition focus:outline-none focus:ring-2 ${
                fieldErrors.title
                  ? "border-rose-400 focus:ring-rose-300"
                  : "border-slate-300 focus:border-teal-500 focus:ring-teal-200"
              }`}
              placeholder="Ej: Paquete no entregado"
            />
            {fieldErrors.title && (
              <p className="mt-1 text-xs font-medium text-rose-600">{fieldErrors.title}</p>
            )}
          </div>

          {/* Descripcion */}
          <div>
            <label htmlFor="description" className="block text-sm font-semibold text-slate-700">
              Descripcion *
            </label>
            <textarea
              id="description"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className={`mt-1 block w-full rounded-lg border px-3 py-2 text-sm shadow-sm transition focus:outline-none focus:ring-2 ${
                fieldErrors.description
                  ? "border-rose-400 focus:ring-rose-300"
                  : "border-slate-300 focus:border-teal-500 focus:ring-teal-200"
              }`}
              placeholder="Describe la incidencia con detalle"
            />
            {fieldErrors.description && (
              <p className="mt-1 text-xs font-medium text-rose-600">{fieldErrors.description}</p>
            )}
          </div>

          {/* Fila: Categoria, Estado, Origen */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="category" className="block text-sm font-semibold text-slate-700">
                Categoria *
              </label>
              <select
                id="category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className={`mt-1 block w-full rounded-lg border px-3 py-2 text-sm shadow-sm transition focus:outline-none focus:ring-2 ${
                  fieldErrors.category
                    ? "border-rose-400 focus:ring-rose-300"
                    : "border-slate-300 focus:border-teal-500 focus:ring-teal-200"
                }`}
              >
                <option value="">Selecciona...</option>
                {CATEGORIES.map((cat) => (
                  <option key={cat.value} value={cat.value}>
                    {cat.label}
                  </option>
                ))}
              </select>
              {fieldErrors.category && (
                <p className="mt-1 text-xs font-medium text-rose-600">{fieldErrors.category}</p>
              )}
            </div>

            <div>
              <label htmlFor="status" className="block text-sm font-semibold text-slate-700">
                Estado
              </label>
              <select
                id="status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm transition focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-200"
              >
                {STATUSES.map((st) => (
                  <option key={st.value} value={st.value}>
                    {st.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="origin" className="block text-sm font-semibold text-slate-700">
                Origen *
              </label>
              <select
                id="origin"
                value={origin}
                onChange={(e) => {
                  setOrigin(e.target.value);
                  if (e.target.value !== "branch" && branch === "") {
                    setBranch("central");
                  }
                }}
                className={`mt-1 block w-full rounded-lg border px-3 py-2 text-sm shadow-sm transition focus:outline-none focus:ring-2 ${
                  fieldErrors.origin
                    ? "border-rose-400 focus:ring-rose-300"
                    : "border-slate-300 focus:border-teal-500 focus:ring-teal-200"
                }`}
              >
                {ORIGINS.map((or) => (
                  <option key={or.value} value={or.value}>
                    {or.label}
                  </option>
                ))}
              </select>
              {fieldErrors.origin && (
                <p className="mt-1 text-xs font-medium text-rose-600">{fieldErrors.origin}</p>
              )}
            </div>
          </div>

          {/* Sede - destacada cuando origin es branch */}
          <div
            className={`rounded-xl border-2 p-4 transition ${
              isBranchHighlighted
                ? "border-teal-400 bg-teal-50"
                : "border-transparent"
            }`}
          >
            <div className="flex items-center gap-2">
              <label htmlFor="branch" className="block text-sm font-semibold text-slate-700">
                Sede *
              </label>
              {isBranchHighlighted && (
                <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs font-medium text-teal-800">
                  Reportando desde sede
                </span>
              )}
            </div>
            <select
              id="branch"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              className={`mt-1 block w-full rounded-lg border px-3 py-2 text-sm shadow-sm transition focus:outline-none focus:ring-2 ${
                fieldErrors.branch
                  ? "border-rose-400 focus:ring-rose-300"
                  : "border-slate-300 focus:border-teal-500 focus:ring-teal-200"
              }`}
            >
              <option value="">Selecciona una sede...</option>
              {BRANCHES.map((br) => (
                <option key={br.value} value={br.value}>
                  {br.label}
                </option>
              ))}
            </select>
            {fieldErrors.branch && (
              <p className="mt-1 text-xs font-medium text-rose-600">{fieldErrors.branch}</p>
            )}
          </div>

          {/* Boton de envio */}
          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={isLoading}
              className="inline-flex items-center gap-2 rounded-lg bg-teal-700 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading && (
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              )}
              {isLoading ? "Registrando..." : "Registrar incidencia"}
            </button>
          </div>
        </form>
      </article>
    </section>
  );
}