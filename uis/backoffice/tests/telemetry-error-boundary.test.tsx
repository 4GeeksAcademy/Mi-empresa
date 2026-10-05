import { act } from "react";
import { createRoot } from "react-dom/client";
import { TelemetryErrorBoundary } from "../components/telemetry-error-boundary";
import { track } from "../lib/telemetry";

jest.mock("../lib/telemetry", () => ({ track: jest.fn() }));

function BrokenSection(): never {
  throw new Error("synthetic-private-message");
}

describe("TelemetryErrorBoundary", () => {
  it("captures a controlled error code without message or stack", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const consoleError = jest.spyOn(console, "error").mockImplementation(() => {});
    try {
      await act(async () => {
        root.render(
          <TelemetryErrorBoundary route="/backoffice/inventory/products">
            <BrokenSection />
          </TelemetryErrorBoundary>,
        );
      });
      expect(track).toHaveBeenCalledWith("frontend_error_captured", {
        error_code: "javascript_error",
        route: "/backoffice/inventory/products",
        release: "backoffice-0.1.0",
      });
      expect(JSON.stringify(jest.mocked(track).mock.calls)).not.toContain("synthetic-private-message");
    } finally {
      await act(async () => root.unmount());
      consoleError.mockRestore();
      container.remove();
    }
  });
});