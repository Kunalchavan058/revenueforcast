import { z } from "zod";

/** Liveness does not imply a ready database, dataset, or trained model. */
export const healthResponseSchema = z.object({
  status: z.literal("ok"),
  service: z.literal("retailforecast-api"),
  api_version: z.literal("v1"),
});

export type HealthResponse = z.infer<typeof healthResponseSchema>;
