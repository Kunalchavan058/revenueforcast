import { z } from "zod";
import { apiRequest } from "./transport";

const datasetSchema = z.object({
  id: z.string().uuid(),
  source: z.string(),
  checksum: z.string(),
  version: z.string(),
  ingested_at: z.iso.datetime({ offset: true }),
  rows: z.number().int().nonnegative(),
  available_through: z.iso.date(),
  availability_policy: z.string(),
});
export const datasetStatusSchema = z.object({
  latest: datasetSchema.nullable(),
  active_model_dataset_version_id: z.string().uuid().nullable(),
  source_kind: z.literal("imported_historical_snapshot"),
  notice: z.string(),
});
export const storePageSchema = z.object({
  dataset_version_id: z.string().uuid().nullable(),
  source_available_through: z.iso.date().nullable(),
  page: z.number().int().positive(),
  page_size: z.number().int().min(1).max(100),
  total: z.number().int().nonnegative(),
  items: z.array(
    z.object({
      store_id: z.number().int().positive(),
      store_type: z.string().nullable(),
      assortment: z.string().nullable(),
      forecast_supported: z.boolean(),
    }),
  ),
});
export type DatasetStatus = z.infer<typeof datasetStatusSchema>;
export type StorePage = z.infer<typeof storePageSchema>;

/** Inspect latest import metadata; ingestion time is not the latest observed business date. */
export function fetchDatasetStatus(
  signal?: AbortSignal,
): Promise<DatasetStatus> {
  return apiRequest("/datasets/status", datasetStatusSchema, { signal });
}
