import catalog from "../../../docs/telemetry/event-schemas.json";
import runtimeRules from "../../../docs/telemetry/runtime-rules.json";

type PropertyRule = { name: string; type: string; required: boolean; allowed_values?: unknown[] };
type EventRule = { event_type: string; producer: string; properties: PropertyRule[]; allowlist: string[] };
const events = new Map<string, EventRule>(catalog.events.map((event) => [event.event_type, event]));
const values: Record<string, unknown[]> = runtimeRules.values;
const eventValues: Record<string, Record<string, unknown[]>> = runtimeRules.eventValues;
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface TelemetryEvent {
  eventId: string;
  timestamp: string;
  sessionId: string | null;
  userId: string | null;
  event_type: string;
  schemaVersion: string;
  requestId: string;
  properties: Record<string, unknown>;
}

export function normalizedRoute(value: string): string {
  const path = value.split(/[?#]/)[0];
  return runtimeRules.routes.find((template) => {
    const pattern = template.split(/\{[^}]+\}/).map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[0-9]+");
    return new RegExp(`^${pattern}$`).test(path);
  }) ?? "/unknown";
}

export function validateProperties(eventType: string, properties: Record<string, unknown>): Record<string, unknown> | null {
  const rule = events.get(eventType);
  if (!rule || Object.keys(properties).some((name) => !rule.allowlist.includes(name))) return null;
  const result: Record<string, unknown> = {};
  for (const prop of rule.properties) {
    if (!Object.hasOwn(properties, prop.name)) {
      if (prop.required) return null;
      continue;
    }
    let value = properties[prop.name];
    if (prop.type === "integer") {
      const minimum = runtimeRules.positiveIntegers.includes(prop.name) ? 1 : 0;
      if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) return null;
      if (["status_code", "http_status"].includes(prop.name) && (value < 100 || value > 599)) return null;
    } else if (prop.type === "string") {
      if (typeof value !== "string") return null;
      let stringValue = value;
      if (prop.name === "route") stringValue = normalizedRoute(stringValue);
      if (prop.name === "sku") {
        stringValue = stringValue.trim().toUpperCase();
        if (!/^[A-Z0-9][A-Z0-9._-]{0,63}$/.test(stringValue)) return null;
      }
      const allowed = prop.allowed_values ?? eventValues[eventType]?.[prop.name] ?? values[prop.name];
      if (allowed ? !allowed.includes(stringValue) : !["sku", "route"].includes(prop.name)) return null;
      value = stringValue;
    } else return null;
    result[prop.name] = value;
  }
  return result;
}

type Workflow = { started: number; step: string; active: boolean; timer?: ReturnType<typeof setTimeout> };

export class TelemetryService {
  private queue: TelemetryEvent[] = [];
  private pending: { events: TelemetryEvent[]; retries: number } | null = null;
  private sending = false;
  private timer?: ReturnType<typeof setInterval>;
  private retryTimer?: ReturnType<typeof setTimeout>;
  private sessionId: string | null = null;
  private userId: string | null = null;
  private views = new Map<string, number>();
  private errors = new Map<string, number>();
  private errorTimes: number[] = [];
  private workflows = new Map<string, Workflow>();

  constructor(private readonly endpoint = process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT ?? "/api/telemetry/events") {}

  private ensureSession(): string {
    if (this.sessionId) return this.sessionId;
    try {
      const stored = sessionStorage.getItem("trackflow_telemetry_session");
      this.sessionId = stored && uuidPattern.test(stored) ? stored : crypto.randomUUID();
      sessionStorage.setItem("trackflow_telemetry_session", this.sessionId);
    } catch {
      this.sessionId = crypto.randomUUID();
    }
    return this.sessionId;
  }

  setUser(userId: string | null): void {
    if (userId !== null && !/^[1-9][0-9]*$/.test(userId)) return;
    let storedActor: string | null = null;
    try { storedActor = sessionStorage.getItem("trackflow_telemetry_actor"); } catch {}
    if (this.userId === userId && storedActor === userId) return;
    this.userId = userId;
    if (storedActor === userId) {
      this.ensureSession();
      return;
    }
    this.sessionId = crypto.randomUUID();
    this.views.clear();
    this.errors.clear();
    this.errorTimes = [];
    this.workflows.forEach((flow) => clearTimeout(flow.timer));
    this.workflows.clear();
    try {
      sessionStorage.setItem("trackflow_telemetry_session", this.sessionId);
      if (userId === null) sessionStorage.removeItem("trackflow_telemetry_actor");
      else sessionStorage.setItem("trackflow_telemetry_actor", userId);
    } catch {}
  }

  correlationHeaders(): Record<string, string> {
    if (typeof window === "undefined") return {};
    return { "X-Request-ID": crypto.randomUUID(), "X-Session-ID": this.ensureSession() };
  }

  track(eventType: string, properties: Record<string, unknown>): void {
    if (typeof window === "undefined" || events.get(eventType)?.producer !== "frontend") return;
    const validated = validateProperties(eventType, properties);
    if (!validated) return;
    const now = Date.now();
    if (eventType === "backoffice_section_viewed") {
      const key = JSON.stringify(validated);
      if (now - (this.views.get(key) ?? -Infinity) < 10000) return;
      if (this.views.size >= 1000) this.views.clear();
      this.views.set(key, now);
    }
    if (eventType === "frontend_error_captured") {
      const key = JSON.stringify(validated);
      this.errorTimes = this.errorTimes.filter((time) => now - time < 60000);
      if (now - (this.errors.get(key) ?? -Infinity) < 60000 || this.errorTimes.length >= 20) return;
      if (this.errors.size >= 1000) this.errors.clear();
      this.errors.set(key, now);
      this.errorTimes.push(now);
    }
    if (this.queue.length >= 200) return;
    this.queue.push({
      eventId: crypto.randomUUID(), timestamp: new Date(now).toISOString(),
      sessionId: this.ensureSession(), userId: this.userId, event_type: eventType,
      schemaVersion: runtimeRules.schemaVersion, requestId: crypto.randomUUID(), properties: validated,
    });
    if (this.queue.length >= 20) void this.flush();
  }

  start(): void {
    if (this.timer || typeof window === "undefined") return;
    this.ensureSession();
    this.timer = setInterval(() => { void this.flush(); }, 10000);
    document.addEventListener("visibilitychange", this.onVisibility);
    window.addEventListener("error", this.onError);
    window.addEventListener("unhandledrejection", this.onRejection);
    window.addEventListener("pagehide", this.onPageHide);
  }

  stop(): void {
    clearInterval(this.timer);
    clearTimeout(this.retryTimer);
    this.timer = undefined;
    this.retryTimer = undefined;
    this.workflows.forEach((flow) => clearTimeout(flow.timer));
    this.workflows.clear();
    document.removeEventListener("visibilitychange", this.onVisibility);
    window.removeEventListener("error", this.onError);
    window.removeEventListener("unhandledrejection", this.onRejection);
    window.removeEventListener("pagehide", this.onPageHide);
  }

  async flush(): Promise<void> {
    if (this.sending || this.retryTimer || (!this.pending && !this.queue.length)) return;
    this.pending ??= { events: this.queue.splice(0, 20), retries: 0 };
    const batch = this.pending;
    this.sending = true;
    try {
      const response = await fetch(this.endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events: batch.events }), signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error("telemetry_delivery_failed");
      this.pending = null;
    } catch {
      if (batch.retries < 3) {
        const delay = 1000 * 2 ** batch.retries++;
        this.retryTimer = setTimeout(() => {
          this.retryTimer = undefined;
          void this.flush();
        }, delay);
      } else this.pending = null;
    } finally {
      this.sending = false;
      if (!this.pending && this.queue.length >= 20) void this.flush();
    }
  }

  flushBeacon(): void {
    if (typeof navigator.sendBeacon !== "function") return;
    if (this.pending && !this.sending) {
      if (!navigator.sendBeacon(this.endpoint, new Blob([JSON.stringify({ events: this.pending.events })], { type: "application/json" }))) return;
      clearTimeout(this.retryTimer);
      this.retryTimer = undefined;
      this.pending = null;
    }
    while (this.queue.length) {
      const batch = this.queue.slice(0, 20);
      if (!navigator.sendBeacon(this.endpoint, new Blob([JSON.stringify({ events: batch })], { type: "application/json" }))) break;
      this.queue.splice(0, batch.length);
    }
  }

  beginWorkflow(name: string): void {
    if (!values.workflow.includes(name)) return;
    const existing = this.workflows.get(name);
    clearTimeout(existing?.timer);
    this.workflows.set(name, { started: existing?.started ?? Date.now(), step: "form_started", active: true });
  }

  submitWorkflow(name: string): void {
    const flow = this.workflows.get(name);
    if (flow) {
      clearTimeout(flow.timer);
      flow.timer = undefined;
      flow.step = "form_submitted";
    }
  }

  completeWorkflow(name: string): void {
    clearTimeout(this.workflows.get(name)?.timer);
    this.workflows.delete(name);
  }

  leaveWorkflow(name: string): void {
    const flow = this.workflows.get(name);
    if (!flow) return;
    flow.active = false;
    this.scheduleAbandonment(name, flow);
  }

  resumeWorkflow(name: string): void {
    const flow = this.workflows.get(name);
    if (!flow) return;
    flow.active = true;
    clearTimeout(flow.timer);
    flow.timer = undefined;
  }

  private scheduleAbandonment(name: string, flow: Workflow): void {
    if (flow.timer || flow.step === "form_submitted") return;
    flow.timer = setTimeout(() => {
      this.track("workflow_abandoned", { workflow: name, last_step: flow.step, duration_ms: Date.now() - flow.started });
      this.workflows.delete(name);
    }, runtimeRules.workflowTimeoutMs);
  }

  private onVisibility = (): void => {
    if (document.visibilityState === "hidden") {
      this.workflows.forEach((flow, name) => { if (flow.active) this.scheduleAbandonment(name, flow); });
      this.flushBeacon();
    } else {
      this.workflows.forEach((flow) => { if (flow.active) { clearTimeout(flow.timer); flow.timer = undefined; } });
    }
  };
  private onPageHide = (): void => { this.flushBeacon(); };
  private onError = (): void => { this.captureError("javascript_error"); };
  private onRejection = (): void => { this.captureError("unhandled_rejection"); };
  private captureError(code: string): void {
    this.track("frontend_error_captured", { error_code: code, route: window.location.pathname, release: "backoffice-0.1.0" });
  }
}

export const telemetry = new TelemetryService();
export function track(eventType: string, properties: Record<string, unknown>): void {
  telemetry.track(eventType, properties);
}