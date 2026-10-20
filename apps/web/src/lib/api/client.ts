import { healthResponseSchema, type HealthResponse } from "./schemas";
import { apiRequest } from "./transport";

export const HEALTH_REQUEST_TIMEOUT_MS = 5000;

/** API liveness has its own short timeout and does not imply model readiness. */
export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest(
    "/health",
    healthResponseSchema,
    { signal },
    HEALTH_REQUEST_TIMEOUT_MS,
  );
}
