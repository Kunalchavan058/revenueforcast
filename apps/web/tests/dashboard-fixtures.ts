import type {
  ForecastInput,
  ForecastResponse,
  ForecastView,
  HistorySummary,
  HistoryQuery,
} from "@/lib/api/dashboards";

// Explicitly synthetic hand-sized transport fixtures, never production fallback data.
export const SOURCE_ID = "11111111-1111-4111-8111-111111111111";
export const MODEL_ID = "22222222-2222-4222-8222-222222222222";
export const FORECAST_ID = "33333333-3333-4333-8333-333333333333";
export const coverage = {
  dataset_version_id: SOURCE_ID,
  checksum: "synthetic-fixture",
  observed_from: "2015-07-01",
  observed_through: "2015-07-31",
  store_count: 2,
  default_store_ids: [1, 2],
};
export const model = {
  version_id: MODEL_ID,
  algorithm: "lightgbm" as const,
  generation: 1,
  trained_until: "2015-07-15",
  feature_schema_fingerprint: "fixture-schema",
};
export const options = {
  model,
  coverage,
  stores: [1, 2].map((store_id) => ({
    store_id,
    observed_from: coverage.observed_from,
    observed_through: coverage.observed_through,
  })),
  sales_delay_days: 0,
  max_stores: 32,
  max_horizon: 48,
};

/** Tiny actual report varies with its requested cohort so request integration remains observable. */
export function historyFixture(query: HistoryQuery): HistorySummary {
  const value = String(query.store_ids.length * 3);
  return {
    query,
    checksum: coverage.checksum,
    observed_from: query.start_date,
    observed_through: query.end_date,
    selected_store_count: query.store_ids.length,
    observed_store_days: query.store_ids.length,
    expected_store_days: query.store_ids.length,
    missing_store_days: 0,
    total_sales: value,
    open_store_days: query.store_ids.length,
    closed_store_days: 0,
    closed_positive_sales_days: 0,
    series: [
      {
        period_start: query.start_date,
        period_end: query.end_date,
        covered_from: query.start_date,
        covered_through: query.end_date,
        observed_store_days: query.store_ids.length,
        expected_store_days: query.store_ids.length,
        sales: value,
      },
    ],
    by_store: query.store_ids.map((store_id) => ({
      store_id,
      sales: "3",
      observed_store_days: 1,
      open_store_days: 1,
      closed_store_days: 0,
    })),
    weekdays: [
      { weekday: 5, observations: 1, sales: value, mean_sales: value },
    ],
    sales_unit: "synthetic fixture units",
  };
}

/** One-day fixture exposes the model/version/cutoff and saved exact values read by the UI. */
export function forecastFixture(input: ForecastInput): ForecastResponse {
  const points = input.store_ids.map((store_id) => ({
    store_id,
    target_date: "2015-08-01",
    horizon: 1,
    predicted_sales: "12.5000",
    known_open: null,
    nonnegative_clamped: false,
    closure_adjusted: false,
  }));
  const period = {
    period_start: "2015-08-01",
    period_end: "2015-08-01",
    covered_from: "2015-08-01",
    covered_through: "2015-08-01",
    days_predicted: 1,
    predicted_sales: String(input.store_ids.length * 12.5),
  };
  return {
    forecast_id: FORECAST_ID,
    generated_at: "2026-10-20T12:00:00Z",
    request: input,
    model,
    data: {
      dataset_version_id: SOURCE_ID,
      source_available_through: "2015-07-31",
      actual_data_cutoff: "2015-07-31",
      history: input.store_ids.map((store_id) => ({
        store_id,
        observed_from: "2015-07-01",
        observed_through: "2015-07-31",
        observations: 31,
        missing_days_in_last_28: 0,
      })),
      assumptions: { sales_delay_days: 0 },
    },
    points,
    totals: {
      predicted_sales: period.predicted_sales,
      by_store: points.map((point) => ({
        store_id: point.store_id,
        predicted_sales: point.predicted_sales,
      })),
      daily: [period],
      weekly: [period],
      monthly: [period],
    },
    warnings: ["Synthetic UI transport fixture, not a measured model result."],
  };
}

/** A saved all-store view is derived from the fixture response, not a second prediction. */
export function viewFixture(response: ForecastResponse): ForecastView {
  return {
    forecast_id: response.forecast_id,
    store_ids: response.request.store_ids,
    points: response.points,
    totals: response.totals,
    actual_data_cutoff: response.data.actual_data_cutoff,
    history: response.data.history,
  };
}
