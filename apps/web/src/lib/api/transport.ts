import { z } from "zod";

export const API_REQUEST_TIMEOUT_MS = 10000;

/** One same-origin, timeout-bounded transport shared by health, catalog and job clients. */
export async function apiRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
  timeoutMs = API_REQUEST_TIMEOUT_MS,
): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs);
  const signal = options.signal
    ? AbortSignal.any([options.signal, timeout])
    : timeout;
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    cache: "no-store",
    signal,
  });
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new Error(
      `The API returned an unreadable response (HTTP ${response.status}).`,
    );
  }
  if (!response.ok) {
    const error = z
      .object({ error: z.object({ message: z.string().max(500) }) })
      .safeParse(payload);
    throw new Error(
      error.success
        ? error.data.error.message
        : `Request failed (HTTP ${response.status}).`,
    );
  }
  const result = schema.safeParse(payload);
  if (!result.success)
    throw new Error("The API response did not match the expected contract.");
  return result.data;
}
