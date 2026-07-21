"use client";

import { useMemo, useState } from "react";

type FormValues = {
  nombreCompleto: string;
  cargo: string;
  email: string;
  telefono: string;
  nombreEmpresa: string;
  sitioWeb: string;
  paisOperacionPrincipal: string;
  mercadoObjetivo: string;
  volumenPedidosMensual: string;
  porcentajeDevoluciones: string;
  numeroSkusActivos: string;
  almacenPreferente: string;
  transportistas: string[];
  serviciosInteres: string[];
  sistemasActuales: string;
  retoPrincipal: string;
  fechaObjetivo: string;
  presupuestoRango: string;
  aceptaPolitica: boolean;
  aceptaComunicaciones: boolean;
};

const initialValues: FormValues = {
  nombreCompleto: "",
  cargo: "",
  email: "",
  telefono: "",
  nombreEmpresa: "",
  sitioWeb: "",
  paisOperacionPrincipal: "",
  mercadoObjetivo: "",
  volumenPedidosMensual: "",
  porcentajeDevoluciones: "",
  numeroSkusActivos: "",
  almacenPreferente: "",
  transportistas: [],
  serviciosInteres: [],
  sistemasActuales: "",
  retoPrincipal: "",
  fechaObjetivo: "",
  presupuestoRango: "",
  aceptaPolitica: false,
  aceptaComunicaciones: false,
};

function isEmailValid(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
}

function isPhoneValid(value: string): boolean {
  return /^\+?[0-9\s().-]{7,20}$/.test(value);
}

function validate(values: FormValues): Record<string, string> {
  const errors: Record<string, string> = {};

  if (values.nombreCompleto.trim().length < 3) errors.nombreCompleto = "Minimo 3 caracteres";
  if (values.cargo.trim().length < 2) errors.cargo = "Minimo 2 caracteres";
  if (!isEmailValid(values.email)) errors.email = "Email invalido";
  if (!isPhoneValid(values.telefono)) errors.telefono = "Telefono invalido";
  if (values.nombreEmpresa.trim().length < 2) errors.nombreEmpresa = "Minimo 2 caracteres";

  if (values.sitioWeb.trim().length > 0) {
    try {
      const url = new URL(values.sitioWeb);
      if (url.protocol !== "http:" && url.protocol !== "https:") {
        errors.sitioWeb = "URL invalida";
      }
    } catch {
      errors.sitioWeb = "URL invalida";
    }
  }

  if (!values.paisOperacionPrincipal) errors.paisOperacionPrincipal = "Obligatorio";
  if (!values.mercadoObjetivo) errors.mercadoObjetivo = "Obligatorio";
  if (!values.volumenPedidosMensual) errors.volumenPedidosMensual = "Obligatorio";
  if (!values.almacenPreferente) errors.almacenPreferente = "Obligatorio";
  if (!values.presupuestoRango) errors.presupuestoRango = "Obligatorio";

  const devoluciones = Number(values.porcentajeDevoluciones);
  if (Number.isNaN(devoluciones) || devoluciones < 0 || devoluciones > 100) {
    errors.porcentajeDevoluciones = "Debe estar entre 0 y 100";
  }

  const skus = Number(values.numeroSkusActivos);
  if (!Number.isInteger(skus) || skus < 1) {
    errors.numeroSkusActivos = "Debe ser entero mayor o igual a 1";
  }

  if (values.transportistas.length === 0) {
    errors.transportistas = "Selecciona al menos uno";
  }

  if (values.serviciosInteres.length === 0) {
    errors.serviciosInteres = "Selecciona al menos uno";
  }

  if (values.sistemasActuales.trim().length < 15) {
    errors.sistemasActuales = "Minimo 15 caracteres";
  }

  if (values.retoPrincipal.trim().length < 20) {
    errors.retoPrincipal = "Minimo 20 caracteres";
  }

  if (!values.fechaObjetivo) {
    errors.fechaObjetivo = "Obligatorio";
  }

  if (!values.aceptaPolitica) {
    errors.aceptaPolitica = "Debes aceptar la politica";
  }

  return errors;
}

interface InputProps {
  label: string;
  error?: string;
  children: React.ReactNode;
}

function Field({ label, error, children }: InputProps) {
  return (
    <div>
      <label className="block text-sm font-semibold text-slate-800">{label}</label>
      <div className="mt-1">{children}</div>
      {error ? <p className="mt-1 text-xs font-semibold text-red-700">{error}</p> : null}
    </div>
  );
}

const inputClass =
  "w-full rounded-xl border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-slate-700";

const transportistasOptions = ["UPS", "FedEx", "DHL", "MRW", "SEUR", "Transportista local 1", "Transportista local 2"];
const serviciosOptions = [
  "API de inventario unificada",
  "Endpoint unificado de tracking",
  "Motor de seleccion de transportista",
  "Automatizacion de devoluciones",
  "Agente de CX y tickets unificados",
  "Dashboard ejecutivo en tiempo real",
];

export function ApplyForm() {
  const [values, setValues] = useState<FormValues>(initialValues);
  const [submitted, setSubmitted] = useState(false);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  const isSuccess = submitted && Object.keys(formErrors).length === 0;

  const canShowErrors = useMemo(() => submitted, [submitted]);

  function updateValue<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function toggleArrayValue(key: "transportistas" | "serviciosInteres", value: string) {
    setValues((current) => {
      const hasValue = current[key].includes(value);
      const next = hasValue
        ? current[key].filter((item) => item !== value)
        : [...current[key], value];

      return { ...current, [key]: next };
    });
  }

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);

    const errors = validate(values);
    setFormErrors(errors);

    if (Object.keys(errors).length === 0) {
      setValues(initialValues);
    }
  }

  return (
    <form className="space-y-7" onSubmit={onSubmit} noValidate>
      <fieldset className="rounded-2xl border border-slate-200 p-4 sm:p-5">
        <legend className="px-2 text-sm font-bold" style={{ color: "var(--brand-blue-deep)" }}>Datos personales</legend>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <Field label="Nombre completo *" error={canShowErrors ? formErrors.nombreCompleto : undefined}>
            <input className={inputClass} value={values.nombreCompleto} onChange={(e) => updateValue("nombreCompleto", e.target.value)} />
          </Field>
          <Field label="Cargo *" error={canShowErrors ? formErrors.cargo : undefined}>
            <input className={inputClass} value={values.cargo} onChange={(e) => updateValue("cargo", e.target.value)} />
          </Field>
          <Field label="Email corporativo *" error={canShowErrors ? formErrors.email : undefined}>
            <input className={inputClass} type="email" value={values.email} onChange={(e) => updateValue("email", e.target.value)} />
          </Field>
          <Field label="Telefono de contacto *" error={canShowErrors ? formErrors.telefono : undefined}>
            <input className={inputClass} value={values.telefono} onChange={(e) => updateValue("telefono", e.target.value)} />
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded-2xl border border-slate-200 p-4 sm:p-5">
        <legend className="px-2 text-sm font-bold" style={{ color: "var(--brand-blue-deep)" }}>Perfil de empresa</legend>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <Field label="Nombre de la empresa *" error={canShowErrors ? formErrors.nombreEmpresa : undefined}>
            <input className={inputClass} value={values.nombreEmpresa} onChange={(e) => updateValue("nombreEmpresa", e.target.value)} />
          </Field>
          <Field label="Sitio web corporativo" error={canShowErrors ? formErrors.sitioWeb : undefined}>
            <input className={inputClass} value={values.sitioWeb} onChange={(e) => updateValue("sitioWeb", e.target.value)} placeholder="https://www.tuempresa.com" />
          </Field>
          <Field label="Pais de operacion principal *" error={canShowErrors ? formErrors.paisOperacionPrincipal : undefined}>
            <select className={inputClass} value={values.paisOperacionPrincipal} onChange={(e) => updateValue("paisOperacionPrincipal", e.target.value)}>
              <option value="">Selecciona una opcion</option>
              <option value="US">Estados Unidos</option>
              <option value="ES">Espana</option>
              <option value="US_ES">Estados Unidos y Espana</option>
            </select>
          </Field>
          <Field label="Mercado objetivo principal *" error={canShowErrors ? formErrors.mercadoObjetivo : undefined}>
            <select className={inputClass} value={values.mercadoObjetivo} onChange={(e) => updateValue("mercadoObjetivo", e.target.value)}>
              <option value="">Selecciona una opcion</option>
              <option value="B2B">Marcas e-commerce (B2B)</option>
              <option value="B2C">Consumidor final (B2C)</option>
              <option value="B2B_B2C">Ambos modelos</option>
            </select>
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded-2xl border border-slate-200 p-4 sm:p-5">
        <legend className="px-2 text-sm font-bold" style={{ color: "var(--brand-blue-deep)" }}>Datos operativos actuales</legend>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <Field label="Volumen de pedidos mensual *" error={canShowErrors ? formErrors.volumenPedidosMensual : undefined}>
            <select className={inputClass} value={values.volumenPedidosMensual} onChange={(e) => updateValue("volumenPedidosMensual", e.target.value)}>
              <option value="">Selecciona una opcion</option>
              <option value="0_1000">0 a 1,000 pedidos</option>
              <option value="1001_10000">1,001 a 10,000 pedidos</option>
              <option value="10001_50000">10,001 a 50,000 pedidos</option>
              <option value="50000_plus">Mas de 50,000 pedidos</option>
            </select>
          </Field>
          <Field label="Porcentaje de devoluciones actual (%) *" error={canShowErrors ? formErrors.porcentajeDevoluciones : undefined}>
            <input className={inputClass} type="number" min={0} max={100} step={0.1} value={values.porcentajeDevoluciones} onChange={(e) => updateValue("porcentajeDevoluciones", e.target.value)} />
          </Field>
          <Field label="Numero de SKU activos *" error={canShowErrors ? formErrors.numeroSkusActivos : undefined}>
            <input className={inputClass} type="number" min={1} step={1} value={values.numeroSkusActivos} onChange={(e) => updateValue("numeroSkusActivos", e.target.value)} />
          </Field>
          <Field label="Almacen preferente para iniciar *" error={canShowErrors ? formErrors.almacenPreferente : undefined}>
            <select className={inputClass} value={values.almacenPreferente} onChange={(e) => updateValue("almacenPreferente", e.target.value)}>
              <option value="">Selecciona una opcion</option>
              <option value="los_angeles">Los Angeles</option>
              <option value="zaragoza">Zaragoza</option>
              <option value="ambos">Ambos</option>
            </select>
          </Field>
        </div>

        <div className="mt-6">
          <p className="text-sm font-semibold text-slate-800">Transportistas que ya utilizas *</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {transportistasOptions.map((item) => (
              <label key={item} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm">
                <input
                  type="checkbox"
                  checked={values.transportistas.includes(item)}
                  onChange={() => toggleArrayValue("transportistas", item)}
                  className="h-4 w-4"
                />
                {item}
              </label>
            ))}
          </div>
          {canShowErrors && formErrors.transportistas ? (
            <p className="mt-2 text-xs font-semibold text-red-700">{formErrors.transportistas}</p>
          ) : null}
        </div>
      </fieldset>

      <fieldset className="rounded-2xl border border-slate-200 p-4 sm:p-5">
        <legend className="px-2 text-sm font-bold" style={{ color: "var(--brand-blue-deep)" }}>
          Necesidades y alcance del proyecto
        </legend>

        <div>
          <p className="text-sm font-semibold text-slate-800">Servicios que te interesan *</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {serviciosOptions.map((item) => (
              <label key={item} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm">
                <input
                  type="checkbox"
                  checked={values.serviciosInteres.includes(item)}
                  onChange={() => toggleArrayValue("serviciosInteres", item)}
                  className="h-4 w-4"
                />
                {item}
              </label>
            ))}
          </div>
          {canShowErrors && formErrors.serviciosInteres ? (
            <p className="mt-2 text-xs font-semibold text-red-700">{formErrors.serviciosInteres}</p>
          ) : null}
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <Field label="Sistemas actuales (SGA, ERP, scripts, etc.) *" error={canShowErrors ? formErrors.sistemasActuales : undefined}>
            <textarea className={inputClass} rows={4} value={values.sistemasActuales} onChange={(e) => updateValue("sistemasActuales", e.target.value)} />
          </Field>
          <Field label="Reto principal que quieres resolver *" error={canShowErrors ? formErrors.retoPrincipal : undefined}>
            <textarea className={inputClass} rows={4} value={values.retoPrincipal} onChange={(e) => updateValue("retoPrincipal", e.target.value)} />
          </Field>
          <Field label="Fecha objetivo para iniciar *" error={canShowErrors ? formErrors.fechaObjetivo : undefined}>
            <input className={inputClass} type="date" value={values.fechaObjetivo} onChange={(e) => updateValue("fechaObjetivo", e.target.value)} />
          </Field>
          <Field label="Rango de presupuesto mensual estimado *" error={canShowErrors ? formErrors.presupuestoRango : undefined}>
            <select className={inputClass} value={values.presupuestoRango} onChange={(e) => updateValue("presupuestoRango", e.target.value)}>
              <option value="">Selecciona una opcion</option>
              <option value="menos_5000">Menos de 5,000 EUR</option>
              <option value="5000_15000">5,000 a 15,000 EUR</option>
              <option value="15001_50000">15,001 a 50,000 EUR</option>
              <option value="50000_plus">Mas de 50,000 EUR</option>
            </select>
          </Field>
        </div>
      </fieldset>

      <fieldset className="rounded-2xl border border-slate-200 p-4 sm:p-5">
        <legend className="px-2 text-sm font-bold" style={{ color: "var(--brand-blue-deep)" }}>Consentimiento</legend>
        <div className="space-y-3">
          <label className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-3 text-sm">
            <input type="checkbox" checked={values.aceptaPolitica} onChange={(e) => updateValue("aceptaPolitica", e.target.checked)} className="mt-0.5 h-4 w-4" />
            <span>Acepto la politica de privacidad y el tratamiento de datos. *</span>
          </label>
          {canShowErrors && formErrors.aceptaPolitica ? (
            <p className="text-xs font-semibold text-red-700">{formErrors.aceptaPolitica}</p>
          ) : null}

          <label className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-3 text-sm">
            <input type="checkbox" checked={values.aceptaComunicaciones} onChange={(e) => updateValue("aceptaComunicaciones", e.target.checked)} className="mt-0.5 h-4 w-4" />
            <span>Acepto recibir comunicaciones comerciales de TrackFlow.</span>
          </label>
        </div>
      </fieldset>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-slate-600">Validamos esta informacion para asegurar una propuesta precisa.</p>
        <button type="submit" className="inline-flex items-center justify-center rounded-full px-6 py-3 text-sm font-bold text-white" style={{ backgroundColor: "var(--brand-orange)" }}>
          Enviar aplicacion
        </button>
      </div>

      {isSuccess ? (
        <div className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">
          Aplicacion enviada correctamente. Nuestro equipo te contactara en menos de 24 horas habiles.
        </div>
      ) : null}
    </form>
  );
}
