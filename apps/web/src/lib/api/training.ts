import { z } from "zod";
import { apiRequest as request } from "./transport";

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
