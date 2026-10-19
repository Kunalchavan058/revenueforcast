import { healthResponseSchema, type HealthResponse } from "./schemas";

export const HEALTH_REQUEST_TIMEOUT_MS = 5000;

/** Fetch and validate API liveness; HTTP, timeout, and schema failures reject. */
export async function fetchHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const timeoutSignal = AbortSignal.timeout(HEALTH_REQUEST_TIMEOUT_MS);
  const requestSignal = signal
    ? AbortSignal.any([signal, timeoutSignal])
    : timeoutSignal;
  const response = await fetch("/api/v1/health", {
    cache: "no-store",
    signal: requestSignal,
  });
  if (!response.ok) {
    throw new Error(`Health request failed with HTTP ${response.status}`);
  }
  const payload: unknown = await response.json();
  return healthResponseSchema.parse(payload);
}
