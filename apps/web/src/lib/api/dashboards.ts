import { z } from "zod";
import { apiRequest } from "./transport";

export const MAX_SELECTED_STORES = 32;
export const MAX_HISTORY_DAYS = 1096;
export const DEFAULT_STORE_SELECTION = 3;
export const DEFAULT_HORIZON = 7;
export const HISTORY_PREVIEW_DAYS = 28;
const amount = z
  .string()
  .regex(/^\d+(?:\.\d{1,4})?$/)
  .refine((value) => Number.isFinite(Number(value)));
const date = z.iso.date();
export const coverageSchema = z.object({
  dataset_version_id: z.string().uuid(),
  checksum: z.string(),
  observed_from: date,
  observed_through: date,
  store_count: z.number().int().nonnegative(),
  default_store_ids: z.array(z.number().int().positive()),
});
export const coverageResponseSchema = z.object({
  coverage: coverageSchema.nullable(),
});
const querySchema = z.object({
  dataset_version_id: z.string().uuid(),
  store_ids: z.array(z.number().int().positive()),
  start_date: date,
  end_date: date,
  frequency: z.enum(["day", "week", "month"]),
});
export const historySummarySchema = z.object({
  query: querySchema,
  checksum: z.string(),
  observed_from: date.nullable(),
  observed_through: date.nullable(),
  selected_store_count: z.number().int().nonnegative(),
  observed_store_days: z.number().int().nonnegative(),
  expected_store_days: z.number().int().nonnegative(),
  missing_store_days: z.number().int().nonnegative(),
  total_sales: amount.nullable(),
  open_store_days: z.number().int().nonnegative(),
  closed_store_days: z.number().int().nonnegative(),
  closed_positive_sales_days: z.number().int().nonnegative(),
  series: z.array(
    z.object({
      period_start: date,
      period_end: date,
      covered_from: date,
      covered_through: date,
      observed_store_days: z.number().int().nonnegative(),
      expected_store_days: z.number().int().nonnegative(),
      sales: amount.nullable(),
    }),
  ),
  by_store: z.array(
    z.object({
      store_id: z.number().int().positive(),
      sales: amount.nullable(),
      observed_store_days: z.number().int().nonnegative(),
      open_store_days: z.number().int().nonnegative(),
      closed_store_days: z.number().int().nonnegative(),
    }),
  ),
  weekdays: z.array(
    z.object({
      weekday: z.number().int().min(1).max(7),
      observations: z.number().int().nonnegative(),
      sales: amount.nullable(),
      mean_sales: amount.nullable(),
    }),
  ),
  sales_unit: z.string(),
});
const modelSchema = z.object({
  version_id: z.string().uuid(),
  algorithm: z.enum(["xgboost", "lightgbm"]),
  generation: z.number().int().nonnegative(),
  trained_until: date,
  feature_schema_fingerprint: z.string(),
});
const storeCoverageSchema = z.object({
  store_id: z.number().int().positive(),
  observed_from: date,
  observed_through: date,
});
export const forecastOptionsSchema = z.object({
  model: modelSchema.nullable(),
  coverage: coverageSchema.nullable(),
  stores: z.array(storeCoverageSchema),
  sales_delay_days: z.number().int().nonnegative(),
  max_stores: z.number().int().positive(),
  max_horizon: z.number().int().positive(),
});
const pointSchema = z.object({
  store_id: z.number().int().positive(),
  target_date: date,
  horizon: z.number().int().min(1).max(48),
  predicted_sales: amount,
  known_open: z.boolean().nullable(),
  nonnegative_clamped: z.boolean(),
  closure_adjusted: z.boolean(),
});
const periodSchema = z.object({
  period_start: date,
  period_end: date,
  covered_from: date,
  covered_through: date,
  days_predicted: z.number().int().positive(),
  predicted_sales: amount,
});
const totalsSchema = z.object({
  predicted_sales: amount,
  by_store: z.array(
    z.object({
      store_id: z.number().int().positive(),
      predicted_sales: amount,
    }),
  ),
  daily: z.array(periodSchema),
  weekly: z.array(periodSchema),
  monthly: z.array(periodSchema),
});
const historyCoverageSchema = storeCoverageSchema.extend({
  observations: z.number().int().nonnegative(),
  missing_days_in_last_28: z.number().int().nonnegative(),
});
export const forecastResponseSchema = z.object({
  forecast_id: z.string().uuid(),
  generated_at: z.iso.datetime({ offset: true }),
  request: z.object({
    store_ids: z.array(z.number().int().positive()),
    cutoff_date: date,
    horizon_days: z.number().int().min(1).max(48),
  }),
  model: modelSchema,
  data: z.object({
    dataset_version_id: z.string().uuid(),
    source_available_through: date,
    actual_data_cutoff: date,
    history: z.array(historyCoverageSchema),
    assumptions: z.object({ sales_delay_days: z.number().int().nonnegative() }),
  }),
  points: z.array(pointSchema),
  totals: totalsSchema,
  warnings: z.array(z.string()),
});
export const forecastViewSchema = z.object({
  forecast_id: z.string().uuid(),
  store_ids: z.array(z.number().int().positive()),
  points: z.array(pointSchema),
  totals: totalsSchema,
  actual_data_cutoff: date,
  history: z.array(historyCoverageSchema),
});
export type SourceCoverage = z.infer<typeof coverageSchema>;
export type HistorySummary = z.infer<typeof historySummarySchema>;
export type HistoryQuery = z.infer<typeof querySchema>;
export type ForecastOptions = z.infer<typeof forecastOptionsSchema>;
export type ForecastResponse = z.infer<typeof forecastResponseSchema>;
export type ForecastView = z.infer<typeof forecastViewSchema>;
export type ForecastInput = {
  store_ids: number[];
  cutoff_date: string;
  horizon_days: number;
};

/** Preserve the exact source/cohort/date/grain in requests and downloadable observed totals. */
export function historyPath(query: HistoryQuery, download = false): string {
  const params = new URLSearchParams({
    dataset_version_id: query.dataset_version_id,
    start_date: query.start_date,
    end_date: query.end_date,
    frequency: query.frequency,
  });
  query.store_ids.forEach((id) => params.append("store_ids", String(id)));
  return `/history/${download ? "download.csv" : "summary"}?${params}`;
}

/** Only the explicit Generate action calls prediction; no training import exists in this client. */
export function generateForecast(
  input: ForecastInput,
): Promise<ForecastResponse> {
  return apiRequest(
    "/forecasts",
    forecastResponseSchema,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
    120000,
  );
}
