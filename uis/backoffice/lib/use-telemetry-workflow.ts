"use client";

import { useEffect } from "react";
import { telemetry } from "./telemetry";

export function useTelemetryWorkflow(name: string) {
  useEffect(() => {
    telemetry.resumeWorkflow(name);
    return () => telemetry.leaveWorkflow(name);
  }, [name]);
  return {
    begin: () => telemetry.beginWorkflow(name),
    submit: () => telemetry.submitWorkflow(name),
    complete: () => telemetry.completeWorkflow(name),
    fail: () => telemetry.beginWorkflow(name),
  };
}