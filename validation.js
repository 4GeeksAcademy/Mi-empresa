const form = document.getElementById("application-form");
const successMessage = document.getElementById("success-message");

const fields = {
  nombre_completo: {
    required: true,
    minLength: 3,
    label: "Nombre completo",
  },
  cargo: {
    required: true,
    minLength: 2,
    label: "Cargo",
  },
  email: {
    required: true,
    type: "email",
    label: "Email corporativo",
  },
  telefono: {
    required: true,
    type: "telefono",
    label: "Telefono de contacto",
  },
  nombre_empresa: {
    required: true,
    minLength: 2,
    label: "Nombre de la empresa",
  },
  sitio_web: {
    required: false,
    type: "url",
    label: "Sitio web corporativo",
  },
  pais_operacion_principal: {
    required: true,
    type: "select",
    label: "Pais de operacion principal",
  },
  mercado_objetivo: {
    required: true,
    type: "select",
    label: "Mercado objetivo principal",
  },
  volumen_pedidos_mensual: {
    required: true,
    type: "select",
    label: "Volumen de pedidos mensual",
  },
  porcentaje_devoluciones: {
    required: true,
    type: "number",
    min: 0,
    max: 100,
    label: "Porcentaje de devoluciones actual",
  },
  numero_skus_activos: {
    required: true,
    type: "integer",
    min: 1,
    label: "Numero de SKU activos",
  },
  almacen_preferente: {
    required: true,
    type: "select",
    label: "Almacen preferente para iniciar",
  },
  sistemas_actuales: {
    required: true,
    minLength: 15,
    label: "Sistemas actuales",
  },
  reto_principal: {
    required: true,
    minLength: 20,
    label: "Reto principal",
  },
  fecha_objetivo: {
    required: true,
    type: "date",
    label: "Fecha objetivo para iniciar",
  },
  presupuesto_rango: {
    required: true,
    type: "select",
    label: "Rango de presupuesto mensual estimado",
  },
  acepta_politica: {
    required: true,
    type: "checkbox",
    label: "Politica de privacidad",
  },
};

const groupRules = [
  {
    name: "transportistas",
    errorId: "transportistas-error",
    message: "Selecciona al menos un transportista actual.",
  },
  {
    name: "servicios_interes",
    errorId: "servicios_interes-error",
    message: "Selecciona al menos un servicio de interes.",
  },
];

const patterns = {
  email: /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/,
  telefono: /^\+?[0-9\s().-]{7,20}$/,
};

function getInput(fieldName) {
  return document.getElementById(fieldName);
}

function getErrorElement(fieldName) {
  return document.getElementById(`${fieldName}-error`);
}

function showError(input, errorElement, message) {
  errorElement.textContent = message;
  errorElement.classList.remove("hidden");

  if (input) {
    input.setAttribute("aria-invalid", "true");
    input.classList.add("border-red-600", "ring-2", "ring-red-200");
    input.classList.remove("border-slate-300");
  }
}

function clearError(input, errorElement) {
  errorElement.textContent = "";
  errorElement.classList.add("hidden");

  if (input) {
    input.setAttribute("aria-invalid", "false");
    input.classList.remove("border-red-600", "ring-2", "ring-red-200");
    input.classList.add("border-slate-300");
  }
}

function validateField(fieldName) {
  const config = fields[fieldName];
  const input = getInput(fieldName);
  const errorElement = getErrorElement(fieldName);

  if (!config || !input || !errorElement) {
    return true;
  }

  const rawValue = input.type === "checkbox" ? input.checked : input.value;
  const value = typeof rawValue === "string" ? rawValue.trim() : rawValue;

  if (config.required) {
    if (input.type === "checkbox" && !input.checked) {
      showError(input, errorElement, `Debes aceptar ${config.label.toLowerCase()}.`);
      return false;
    }

    if (value === "") {
      showError(input, errorElement, `${config.label} es obligatorio.`);
      return false;
    }
  }

  if (!config.required && value === "") {
    clearError(input, errorElement);
    return true;
  }

  if (config.minLength && typeof value === "string" && value.length < config.minLength) {
    showError(input, errorElement, `${config.label} debe tener al menos ${config.minLength} caracteres.`);
    return false;
  }

  if (config.type === "email" && !patterns.email.test(value)) {
    showError(input, errorElement, "Ingresa un email corporativo valido (ejemplo@empresa.com).");
    return false;
  }

  if (config.type === "telefono" && !patterns.telefono.test(value)) {
    showError(input, errorElement, "Ingresa un telefono valido con prefijo o formato internacional.");
    return false;
  }

  if (config.type === "url") {
    try {
      const url = new URL(value);
      if (!["http:", "https:"].includes(url.protocol)) {
        throw new Error("Protocol not supported");
      }
    } catch {
      showError(input, errorElement, "Ingresa una URL valida (incluye http:// o https://).");
      return false;
    }
  }

  if (config.type === "select" && value === "") {
    showError(input, errorElement, `Selecciona una opcion en ${config.label.toLowerCase()}.`);
    return false;
  }

  if (config.type === "number") {
    const numericValue = Number(value);
    if (Number.isNaN(numericValue)) {
      showError(input, errorElement, `${config.label} debe ser un numero valido.`);
      return false;
    }
    if (typeof config.min === "number" && numericValue < config.min) {
      showError(input, errorElement, `${config.label} no puede ser menor que ${config.min}.`);
      return false;
    }
    if (typeof config.max === "number" && numericValue > config.max) {
      showError(input, errorElement, `${config.label} no puede ser mayor que ${config.max}.`);
      return false;
    }
  }

  if (config.type === "integer") {
    const numericValue = Number(value);
    if (!Number.isInteger(numericValue)) {
      showError(input, errorElement, `${config.label} debe ser un numero entero.`);
      return false;
    }
    if (typeof config.min === "number" && numericValue < config.min) {
      showError(input, errorElement, `${config.label} debe ser mayor o igual a ${config.min}.`);
      return false;
    }
  }

  if (config.type === "date") {
    const selectedDate = new Date(value);
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    if (Number.isNaN(selectedDate.getTime())) {
      showError(input, errorElement, "Selecciona una fecha valida.");
      return false;
    }

    if (selectedDate < today) {
      showError(input, errorElement, "La fecha objetivo no puede ser anterior a hoy.");
      return false;
    }
  }

  clearError(input, errorElement);
  return true;
}

function validateCheckboxGroup(rule) {
  const checkboxes = Array.from(form.querySelectorAll(`input[name="${rule.name}"]`));
  const errorElement = document.getElementById(rule.errorId);
  const hasSelection = checkboxes.some((checkbox) => checkbox.checked);

  if (!errorElement || checkboxes.length === 0) {
    return true;
  }

  checkboxes.forEach((checkbox) => {
    checkbox.classList.remove("ring-2", "ring-red-200");
    checkbox.setAttribute("aria-invalid", "false");
  });

  if (!hasSelection) {
    errorElement.textContent = rule.message;
    errorElement.classList.remove("hidden");
    checkboxes.forEach((checkbox) => {
      checkbox.classList.add("ring-2", "ring-red-200");
      checkbox.setAttribute("aria-invalid", "true");
    });
    return false;
  }

  errorElement.textContent = "";
  errorElement.classList.add("hidden");
  return true;
}

function validateAllFields() {
  const fieldResults = Object.keys(fields).map((fieldName) => validateField(fieldName));
  const groupResults = groupRules.map((rule) => validateCheckboxGroup(rule));
  return [...fieldResults, ...groupResults].every(Boolean);
}

function bindRealtimeValidation() {
  Object.keys(fields).forEach((fieldName) => {
    const input = getInput(fieldName);
    if (!input) {
      return;
    }

    const isCheckbox = input.type === "checkbox";
    const eventType = isCheckbox ? "change" : "input";

    input.addEventListener(eventType, () => {
      validateField(fieldName);
    });

    input.addEventListener("blur", () => {
      validateField(fieldName);
    });
  });

  groupRules.forEach((rule) => {
    const checkboxes = form.querySelectorAll(`input[name="${rule.name}"]`);
    checkboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        validateCheckboxGroup(rule);
      });
    });
  });
}

if (form) {
  bindRealtimeValidation();

  form.addEventListener("submit", (event) => {
    successMessage.classList.add("hidden");
    successMessage.textContent = "";

    const isValid = validateAllFields();
    if (!isValid) {
      event.preventDefault();

      const firstInvalid = form.querySelector("[aria-invalid='true']");
      if (firstInvalid) {
        firstInvalid.focus();
      }
      return;
    }

    event.preventDefault();
    successMessage.textContent =
      "Aplicacion enviada correctamente. Nuestro equipo de TrackFlow revisara tu informacion y te contactara en menos de 24 horas habiles.";
    successMessage.classList.remove("hidden");
    form.reset();
  });
}
