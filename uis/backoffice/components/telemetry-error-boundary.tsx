"use client";

import { Component, type ReactNode } from "react";
import { track } from "../lib/telemetry";

interface TelemetryErrorBoundaryProps {
  children: ReactNode;
  route: string;
}

interface TelemetryErrorBoundaryState {
  hasError: boolean;
}

export class TelemetryErrorBoundary extends Component<
  TelemetryErrorBoundaryProps,
  TelemetryErrorBoundaryState
> {
  state: TelemetryErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): TelemetryErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(): void {
    track("frontend_error_captured", {
      error_code: "javascript_error",
      route: this.props.route,
      release: "backoffice-0.1.0",
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <main role="alert" className="mx-auto max-w-3xl px-6 py-12">
          <p className="font-semibold">No se pudo mostrar esta sección.</p>
          <button className="mt-4 underline" onClick={() => window.location.reload()}>
            Recargar
          </button>
        </main>
      );
    }
    return this.props.children;
  }
}