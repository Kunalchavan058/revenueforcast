import { z } from "zod";

export const activeSlotSchema = z.object({
  active_model_version_id: z.string().uuid().nullable(),
  generation: z.number().int().nonnegative(),
});
export const trainingJobSchema = z.object({
  id: z.string().uuid(),
  algorithm: z.enum(["auto", "xgboost", "lightgbm"]),
  state: z.enum([
    "queued",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "cancelled",
  ]),
  stage: z.string(),
  message: z.string(),
  attempt_count: z.number().int().nonnegative(),
  max_attempts: z.number().int().positive(),
  model_version_id: z.string().uuid().nullable(),
  worker_required: z.literal(true),
});
export type ActiveSlot = z.infer<typeof activeSlotSchema>;
export type TrainingJob = z.infer<typeof trainingJobSchema>;
export type TrainingAlgorithm = TrainingJob["algorithm"];

const REQUEST_TIMEOUT_MS = 10000;

/** Fetch typed queue state; network/validation failure never implies a ready model. */
async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  const signal = options.signal
    ? AbortSignal.any([options.signal, timeout])
    : timeout;
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    cache: "no-store",
    signal,
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const error = z
      .object({ error: z.object({ message: z.string() }) })
      .safeParse(payload);
    throw new Error(
      error.success
        ? error.data.error.message
        : `Request failed (HTTP ${response.status})`,
    );
  }
  return schema.parse(payload);
}

/** Read the authoritative pointer; liveness alone is insufficient for onboarding. */
export function fetchActiveSlot(signal?: AbortSignal): Promise<ActiveSlot> {
  return request("/models/active", activeSlotSchema, { signal });
}

/** Enqueue only; the server returns before native fitting starts in the standalone worker. */
export function enqueueTraining(
  algorithm: TrainingAlgorithm,
  idempotencyKey: string,
): Promise<TrainingJob> {
  return request("/training-jobs", trainingJobSchema, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ algorithm }),
  });
}

/** Poll durable status, not browser-owned scheduling or training execution. */
export function fetchTrainingJob(
  id: string,
  signal?: AbortSignal,
): Promise<TrainingJob> {
  return request(`/training-jobs/${id}`, trainingJobSchema, { signal });
}
