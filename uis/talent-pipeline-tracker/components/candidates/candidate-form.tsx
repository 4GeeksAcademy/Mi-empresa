"use client";

import { FormEvent, useMemo, useState } from "react";
import { CandidateCreatePayload, CandidateRecord } from "@/types/candidates";

interface CandidateFormProps {
  mode: "create" | "edit";
  initialValue?: CandidateRecord;
  onSubmit: (payload: CandidateCreatePayload) => Promise<void>;
  submitLabel: string;
}

interface FormState {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string;
  cv_url: string;
  experience_years: string;
}

const EMPTY_FORM: FormState = {
  full_name: "",
  email: "",
  phone: "",
  position: "",
  linkedin_url: "",
  cv_url: "",
  experience_years: "",
};

export function CandidateForm({ mode, initialValue, onSubmit, submitLabel }: CandidateFormProps) {
  const [form, setForm] = useState<FormState>(() => {
    if (!initialValue) return EMPTY_FORM;

    return {
      full_name: initialValue.full_name,
      email: initialValue.email,
      phone: initialValue.phone,
      position: initialValue.position,
      linkedin_url: initialValue.linkedin_url ?? "",
      cv_url: initialValue.cv_url ?? "",
      experience_years: String(initialValue.experience_years),
    };
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const title = useMemo(
    () => (mode === "create" ? "Nueva candidatura" : "Editar candidatura"),
    [mode],
  );

  function updateField(key: keyof FormState, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (
      !form.full_name.trim() ||
      !form.email.trim() ||
      !form.phone.trim() ||
      !form.position.trim() ||
      !form.experience_years.trim()
    ) {
      setError("Completa los campos obligatorios antes de enviar.");
      return;
    }

    const years = Number(form.experience_years);
    if (!Number.isFinite(years) || years < 0) {
      setError("Años de experiencia debe ser un número válido mayor o igual a 0.");
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        position: form.position.trim(),
        linkedin_url: form.linkedin_url.trim() || null,
        cv_url: form.cv_url.trim() || null,
        experience_years: years,
      });

      setSuccessMessage(
        mode === "create"
          ? "Candidatura creada correctamente."
          : "Candidatura actualizada correctamente.",
      );

      if (mode === "create") {
        setForm(EMPTY_FORM);
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "No se pudo guardar.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="card p-4 space-y-3" onSubmit={handleSubmit}>
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        {successMessage ? <p className="text-sm text-[var(--ok)]">{successMessage}</p> : null}
      </div>

      {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="text-sm">
          Nombre completo *
          <input
            className="input mt-1"
            value={form.full_name}
            onChange={(event) => updateField("full_name", event.target.value)}
          />
        </label>

        <label className="text-sm">
          Email *
          <input
            className="input mt-1"
            type="email"
            value={form.email}
            onChange={(event) => updateField("email", event.target.value)}
          />
        </label>

        <label className="text-sm">
          Teléfono *
          <input
            className="input mt-1"
            value={form.phone}
            onChange={(event) => updateField("phone", event.target.value)}
          />
        </label>

        <label className="text-sm">
          Puesto *
          <input
            className="input mt-1"
            value={form.position}
            onChange={(event) => updateField("position", event.target.value)}
          />
        </label>

        <label className="text-sm">
          LinkedIn
          <input
            className="input mt-1"
            value={form.linkedin_url}
            onChange={(event) => updateField("linkedin_url", event.target.value)}
          />
        </label>

        <label className="text-sm">
          CV URL
          <input
            className="input mt-1"
            value={form.cv_url}
            onChange={(event) => updateField("cv_url", event.target.value)}
          />
        </label>

        <label className="text-sm md:col-span-2">
          Años de experiencia *
          <input
            className="input mt-1"
            type="number"
            min={0}
            value={form.experience_years}
            onChange={(event) => updateField("experience_years", event.target.value)}
          />
        </label>
      </div>

      <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Guardando..." : submitLabel}
      </button>
    </form>
  );
}
