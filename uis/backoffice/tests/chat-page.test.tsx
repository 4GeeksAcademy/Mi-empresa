import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import ChatPage from "@/app/chat/page";
import { getToken } from "@/lib/auth";

jest.mock("@/lib/auth", () => ({ getToken: jest.fn(() => "jwt"), handleUnauthorized: jest.fn() }));

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) { MockWebSocket.instances.push(this); }
  send(value: string) { this.sent.push(value); }
  close() { this.onclose?.({ code: 1000 }); }
  receive(event: string, data: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify({ event, data }) });
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  Object.defineProperty(global, "WebSocket", { configurable: true, value: MockWebSocket });
  Object.defineProperty(global, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, value: true });
  localStorage.clear();
});

it("streams tokens, interrupts, and sends redirected input on the same session", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root: Root = createRoot(container);
  await act(async () => {
    root.render(<ChatPage />);
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(MockWebSocket.instances).toHaveLength(1);
  const socket = MockWebSocket.instances[0];
  const input = container.querySelector<HTMLTextAreaElement>("textarea");
  const button = container.querySelector<HTMLButtonElement>("button[type='submit']");
  expect(input).not.toBeNull();
  expect(button).not.toBeNull();

  await act(async () => socket.onopen?.());
  await act(async () => socket.receive("session_snapshot", { session_id: "session", messages: [] }));
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(input, "rastrea mi pedido");
    input?.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => button?.click());
  expect(JSON.parse(socket.sent[0])).toMatchObject({ event: "user_message", data: { text: "rastrea mi pedido" } });

  await act(async () => socket.receive("token_chunk", { message_id: "assistant-1", token: "Tu pedido ", sequence: 1 }));
  expect(container.textContent).toContain("Tu pedido");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(input, "No, quiero devolverlo");
    input?.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => button?.click());
  expect(JSON.parse(socket.sent[1])).toMatchObject({ event: "interrupt_requested", data: { new_input: "No, quiero devolverlo" } });
  await act(async () => socket.receive("generation_interrupted", { message_id: "assistant-1", status: "interrupted" }));
  expect(container.textContent).toContain("Respuesta interrumpida · puedes continuar");
  expect(getToken).toHaveBeenCalled();

  await act(async () => root.unmount());
  container.remove();
});
