import { TelemetryService, normalizedRoute, validateProperties } from "../lib/telemetry";

async function settle() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("TelemetryService", () => {
  let service: TelemetryService;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    jest.useFakeTimers();
    sessionStorage.clear();
    let identifier = 0;
    Object.defineProperty(crypto, "randomUUID", { configurable: true, value: () => `00000000-0000-4000-8000-${String(++identifier).padStart(12, "0")}` });
    Object.defineProperty(AbortSignal, "timeout", { configurable: true, value: jest.fn(() => new AbortController().signal) });
    fetchMock = jest.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchMock;
    service = new TelemetryService("/telemetry/events");
    service.start();
  });
  afterEach(() => { service.stop(); jest.useRealTimers(); });

  function capture() {
    service.track("search_executed", { section: "suppliers", filter_type: "country", result_count: 1 });
  }

  it("enqueues timestamps at capture and sends only at 10 seconds", async () => {
    capture();
    expect(fetchMock).not.toHaveBeenCalled();
    const capturedAt = new Date().toISOString();
    await jest.advanceTimersByTimeAsync(10000);
    const event = JSON.parse(fetchMock.mock.calls[0][1].body).events[0];
    expect(event.timestamp).toBe(capturedAt);
    expect(Object.keys(event)).toHaveLength(8);
    expect(event.userId).toBeNull();
  });

  it("sends 20 events and preserves new events while in flight", async () => {
    let resolve: (value: { ok: boolean }) => void = () => {};
    fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    for (let count = 0; count < 20; count++) capture();
    capture();
    await service.flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolve({ ok: true });
    await settle();
    await service.flush();
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).events).toHaveLength(1);
  });

  it("retries three times with identical event IDs then discards", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    capture();
    await service.flush();
    await jest.advanceTimersByTimeAsync(1000);
    await jest.advanceTimersByTimeAsync(2000);
    await jest.advanceTimersByTimeAsync(4000);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(new Set(fetchMock.mock.calls.map((call) => call[1].body)).size).toBe(1);
    await service.flush();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("retains the queue if sendBeacon refuses and clears only accepted batches", async () => {
    const beacon = jest.fn().mockReturnValue(false);
    Object.defineProperty(navigator, "sendBeacon", { configurable: true, value: beacon });
    capture();
    service.flushBeacon();
    expect(beacon).toHaveBeenCalledTimes(1);
    await service.flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    capture();
    beacon.mockReturnValue(true);
    service.flushBeacon();
    await service.flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects PII, backend producers, unknown types and wrong values", async () => {
    service.track("login_succeeded", { auth_method: "password" });
    service.track("unknown", {});
    service.track("backoffice_section_viewed", { section: "inventory", email: "private" });
    service.track("backoffice_section_viewed", { section: "unknown" });
    await service.flush();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(validateProperties("search_executed", { section: "suppliers", filter_type: "country", result_count: -1 })).toBeNull();
    expect(normalizedRoute("/inventory/products/42?token=secret")).toBe("/inventory/products/{product_id}");
  });

  it("rotates sessions without changing already captured actor context", async () => {
    capture();
    service.setUser("12");
    capture();
    service.setUser(null);
    capture();
    await service.flush();
    const events = JSON.parse(fetchMock.mock.calls[0][1].body).events;
    expect(events.map((event: { userId: string | null }) => event.userId)).toEqual([null, "12", null]);
    expect(new Set(events.map((event: { sessionId: string }) => event.sessionId)).size).toBe(3);
  });

  it("restores the authenticated session UUID after a page reload", async () => {
    service.setUser("12");
    const session = sessionStorage.getItem("trackflow_telemetry_session");
    const restored = new TelemetryService("/telemetry/events");
    restored.setUser("12");
    expect(restored.correlationHeaders()["X-Session-ID"]).toBe(session);
    restored.setUser(null);
    expect(restored.correlationHeaders()["X-Session-ID"]).not.toBe(session);
  });

  it("deduplicates navigation and global errors without recording messages", async () => {
    for (let count = 0; count < 2; count++) {
      service.track("backoffice_section_viewed", { section: "inventory", route: "/backoffice/inventory/products?token=secret" });
      window.dispatchEvent(new ErrorEvent("error", { message: "secret@example.com" }));
    }
    await service.flush();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).events).toHaveLength(2);
    expect(fetchMock.mock.calls[0][1].body).not.toContain("secret");
  });

  it("emits abandonment after leaving and timeout, not after completion", async () => {
    service.beginWorkflow("inbound_order");
    service.leaveWorkflow("inbound_order");
    await jest.advanceTimersByTimeAsync(60000);
    await service.flush();
    const bodies = fetchMock.mock.calls.flatMap((call) => JSON.parse(call[1].body).events);
    expect(bodies[0].event_type).toBe("workflow_abandoned");
    service.beginWorkflow("outbound_order");
    service.completeWorkflow("outbound_order");
    service.leaveWorkflow("outbound_order");
    await jest.advanceTimersByTimeAsync(60000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not abandon a workflow resumed before its timeout", async () => {
    service.beginWorkflow("inbound_order");
    service.leaveWorkflow("inbound_order");
    await jest.advanceTimersByTimeAsync(30000);
    service.resumeWorkflow("inbound_order");
    await jest.advanceTimersByTimeAsync(60000);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});