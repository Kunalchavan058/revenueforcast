import {
  HISTORY_PREVIEW_DAYS,
  type ForecastOptions,
  type SourceCoverage,
} from "./api/dashboards";

/** Calendar arithmetic stays at UTC midnight; never choose today's date as a history default. */
export function addDays(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** Start a small actual-data view at the source's latest 28 observed-calendar days. */
export function initialHistoryRange(coverage: SourceCoverage): {
  start: string;
  end: string;
} {
  return {
    start: [
      coverage.observed_from,
      addDays(coverage.observed_through, -HISTORY_PREVIEW_DAYS + 1),
    ]
      .sort()
      .at(-1)!,
    end: coverage.observed_through,
  };
}

/** Use the shared selected-store overlap and saved fit date, including declared label delay. */
export function cutoffBounds(
  options: ForecastOptions,
  storeIds: readonly number[],
): { min: string; max: string } | null {
  if (!options.model || !options.coverage || !storeIds.length) return null;
  const stores = options.stores.filter((store) =>
    storeIds.includes(store.store_id),
  );
  if (stores.length !== storeIds.length) return null;
  const min = [
    options.model.trained_until,
    ...stores.map((store) =>
      addDays(store.observed_from, options.sales_delay_days),
    ),
  ]
    .sort()
    .at(-1)!;
  const max = stores
    .map((store) => addDays(store.observed_through, options.sales_delay_days))
    .sort()[0]!;
  return min <= max ? { min, max } : null;
}
