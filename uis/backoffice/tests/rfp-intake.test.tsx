import { act } from "react";
import { createRoot } from "react-dom/client";
import { RfpIntake } from "../components/rfp-intake";
import { getToken } from "@/lib/auth";

jest.mock("@/lib/auth", () => ({ getToken: jest.fn() }));
jest.mock("../components/rfp-approvals", () => ({ RfpApprovals: () => null }));

const mockedGetToken = jest.mocked(getToken);
Object.defineProperty(global, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true });

class TestTextEncoder {
  encode(value: string) { return new Uint8Array(Buffer.from(value, "utf8")); }
}

Object.defineProperty(global, "TextEncoder", { value: TestTextEncoder, configurable: true });

function streamResponse(frames: string[]) {
  const encoder = new TextEncoder();
  let index = 0;
  const body = {
    getReader: () => ({
      read: async () => index < frames.length
        ? { done: false, value: encoder.encode(frames[index++]) }
        : { done: true, value: undefined },
    }),
  };
  return { ok: true, body } as Response;
}

describe("RfpIntake SSE notifications", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockedGetToken.mockReturnValue("jwt-token");
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it("uses bearer fetch, recovers snapshot, parses named SSE events and deduplicates overlap", async () => {
    const acceptedAt = new Date().toISOString();
    const ticketId = "ticket-123";
    const payload = {
      ticket_id: ticketId, rfp_id: "rfp-123", client_name: "Northline Apparel", client_country: "US",
      services_requested: ["warehouse"], status: "analyzing", created_at: acceptedAt,
    };
    jest.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [{
          ticket_id: ticketId, rfp_id: payload.rfp_id, accepted_at: acceptedAt,
          metadata: { client_name: payload.client_name, client_country: payload.client_country,
            services_requested: payload.services_requested },
        }],
      } as Response)
      .mockResolvedValueOnce(streamResponse([
        `id: ${ticketId}\nevent: rfp_ticket_created\ndata: ${JSON.stringify(payload)}\n\n`,
      ]));

    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => { root.render(<RfpIntake />); await Promise.resolve(); await Promise.resolve(); });
    expect(container.textContent).toContain("Northline Apparel");
    expect(container.textContent?.match(/Ticket ticket-123/g)).toHaveLength(1);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(jest.mocked(fetch).mock.calls[0][0]).toContain("created_after=");
    expect(jest.mocked(fetch).mock.calls[1][0]).toContain("/api/rfps/events?since=");
    for (const [url, options] of jest.mocked(fetch).mock.calls) {
      expect(url).toContain("/api/rfps");
      expect(options?.headers).toEqual({ Authorization: "Bearer jwt-token" });
    }
    await act(async () => root.unmount());
  });

  it("retries interrupted connections using capped exponential backoff and recovers each time", async () => {
    jest.mocked(fetch)
      .mockResolvedValueOnce({ ok: false, json: async () => [] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce(streamResponse([]));
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => { root.render(<RfpIntake />); await Promise.resolve(); });
    await act(async () => { jest.advanceTimersByTime(499); });
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => { jest.advanceTimersByTime(1); await Promise.resolve(); await Promise.resolve(); });
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(jest.mocked(fetch).mock.calls[1][0]).toContain("created_after=");
    expect(jest.mocked(fetch).mock.calls[2][0]).toContain("/api/rfps/events?since=");
    await act(async () => root.unmount());
  });
});