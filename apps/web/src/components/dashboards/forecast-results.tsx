"use client";

import { useState } from "react";
import { ChartShell } from "@/components/foundation/chart-shell";
import { ErrorBanner } from "@/components/foundation/error-banner";
import { MetricCard } from "@/components/foundation/metric-card";
import { Card } from "@/components/ui/card";
import {
  forecastViewSchema,
  historyPath,
  historySummarySchema,
  HISTORY_PREVIEW_DAYS,
  type ForecastResponse,
  type ForecastView,
} from "@/lib/api/dashboards";
import { useApiResource } from "@/lib/api/use-api-resource";
import { addDays } from "@/lib/dashboard-dates";
import { formatDate, formatSales } from "@/lib/format";

/** Load display history only through the returned observed cutoff; later actuals never enter this chart. */
function ForecastChart({
  forecast,
  view,
}: {
  forecast: ForecastResponse;
  view: ForecastView;
}): React.JSX.Element {
  const firstObserved = view.history
    .map((row) => row.observed_from)
    .sort()
    .at(-1)!;
  const start = [
    firstObserved,
    addDays(view.actual_data_cutoff, -HISTORY_PREVIEW_DAYS + 1),
  ]
    .sort()
    .at(-1)!;
  const path = historyPath({
    dataset_version_id: forecast.data.dataset_version_id,
    store_ids: view.store_ids,
    start_date: start,
    end_date: view.actual_data_cutoff,
    frequency: "day",
  });
  const { resource, refresh } = useApiResource(path, historySummarySchema);
  const points = new Map<
    string,
    { date: string; actual: number | null; predicted: number | null }
  >();
  if (resource.state === "ready")
    resource.data.series.forEach((row) =>
      points.set(row.covered_from, {
        date: row.covered_from,
        actual: row.sales === null ? null : Number(row.sales),
        predicted: null,
      }),
    );
  // Insert the actual boundary explicitly even when a categorical chart has a calendar gap.
  if (!points.has(view.actual_data_cutoff))
    points.set(view.actual_data_cutoff, {
      date: view.actual_data_cutoff,
      actual: null,
      predicted: null,
    });
  view.totals.daily.forEach((row) =>
    points.set(row.covered_from, {
      date: row.covered_from,
      actual: null,
      predicted: Number(row.predicted_sales),
    }),
  );
  return (
    <ChartShell
      title="Observed history and predicted sales"
      description={`Source Sales units · last observed date ${formatDate(view.actual_data_cutoff)} · forecast as-of ${formatDate(forecast.request.cutoff_date)}. Historical totals may have partial store-day coverage.`}
      points={[...points.values()]}
      lastObservedDate={view.actual_data_cutoff}
      loading={resource.state === "loading"}
      error={resource.state === "error" ? resource.message : undefined}
      onRetry={refresh}
    />
  );
}

/** Read-only saved subset keeps daily/weekly values consistent with server decimal totals and CSV. */
function ForecastDetail({
  forecast,
  view,
}: {
  forecast: ForecastResponse;
  view: ForecastView;
}): React.JSX.Element {
  const [period, setPeriod] = useState<"daily" | "weekly">("daily");
  const [page, setPage] = useState(1);
  const pageSize = 48;
  const rows = period === "daily" ? view.points : view.totals.weekly;
  const shown = rows.slice((page - 1) * pageSize, page * pageSize);
  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          label="Predicted sales"
          value={formatSales(Number(view.totals.predicted_sales))}
          description="Sum of saved rounded daily estimates, not guaranteed revenue."
        />
        <MetricCard
          label="Forecast as-of"
          value={formatDate(forecast.request.cutoff_date)}
          description={`${forecast.request.horizon_days} days after this fixed cutoff.`}
          icon="forecasts"
        />
        <MetricCard
          label="Active version used"
          value={forecast.model.version_id.slice(0, 8)}
          description={`${forecast.model.algorithm} · fitted through ${formatDate(forecast.model.trained_until)}`}
          icon="models"
        />
      </div>
      <ForecastChart forecast={forecast} view={view} />
      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="font-semibold">Saved predictions</h2>
          <label className="flex items-center gap-3 text-sm">
            Results period
            <select
              aria-label="Prediction results period"
              className="rounded border border-slate-500 bg-card px-3 py-2"
              value={period}
              onChange={(event) => {
                setPeriod(event.target.value as "daily" | "weekly");
                setPage(1);
              }}
            >
              <option value="daily">Daily per store</option>
              <option value="weekly">Weekly total</option>
            </select>
          </label>
        </div>
        <div
          role="region"
          aria-label="Saved prediction rows"
          tabIndex={0}
          className="mt-4 overflow-auto"
        >
          <table className="w-full text-left text-sm">
            <caption className="sr-only">
              Saved predictions in source Sales units; weekly dates may cover
              partial weeks
            </caption>
            <thead>
              <tr>
                <th scope="col" className="p-3">
                  {period === "daily"
                    ? "Target date / store"
                    : "Covered week dates"}
                </th>
                <th scope="col" className="p-3">
                  Predicted sales
                </th>
                <th scope="col" className="p-3">
                  {period === "daily" ? "Horizon" : "Days predicted"}
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) =>
                "store_id" in row ? (
                  <tr
                    key={`${row.store_id}-${row.target_date}`}
                    className="border-t border-border"
                  >
                    <th scope="row" className="p-3 font-normal">
                      {formatDate(row.target_date)} · Store #{row.store_id}
                    </th>
                    <td className="p-3 tabular-nums">
                      {formatSales(Number(row.predicted_sales))}
                    </td>
                    <td className="p-3">Day {row.horizon}</td>
                  </tr>
                ) : (
                  <tr key={row.period_start} className="border-t border-border">
                    <th scope="row" className="p-3 font-normal">
                      {formatDate(row.covered_from)} –{" "}
                      {formatDate(row.covered_through)}
                    </th>
                    <td className="p-3 tabular-nums">
                      {formatSales(Number(row.predicted_sales))}
                    </td>
                    <td className="p-3">{row.days_predicted}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
        {rows.length > pageSize && (
          <div className="mt-4 flex items-center gap-4">
            <button
              type="button"
              className="min-h-11 px-3 text-primary disabled:text-muted-foreground"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              Previous results
            </button>
            <span className="text-xs">
              Page {page} of {Math.ceil(rows.length / pageSize)}
            </span>
            <button
              type="button"
              className="min-h-11 px-3 text-primary disabled:text-muted-foreground"
              disabled={page * pageSize >= rows.length}
              onClick={() => setPage(page + 1)}
            >
              Next results
            </button>
          </div>
        )}
      </Card>
    </div>
  );
}

/** The visible version and source always come from the saved response, even if the active pointer changes. */
export function ForecastResults({
  forecast,
}: {
  forecast: ForecastResponse;
}): React.JSX.Element {
  const [store, setStore] = useState("all");
  const { resource, refresh } = useApiResource(
    `/forecasts/${forecast.forecast_id}/view${store === "all" ? "" : `?store_id=${store}`}`,
    forecastViewSchema,
  );
  return (
    <section className="space-y-6" aria-label="Forecast results">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">Forecast results</h2>
          <p className="mt-2 break-all text-xs text-muted-foreground">
            Model {forecast.model.version_id} · as-of{" "}
            {formatDate(forecast.request.cutoff_date)} · generated{" "}
            {new Date(forecast.generated_at).toISOString()}
          </p>
        </div>
        <a
          href={`/api/v1/forecasts/${forecast.forecast_id}/download.csv`}
          className="inline-flex min-h-11 items-center rounded-md border border-border bg-card px-4 text-sm font-semibold"
        >
          Download forecast CSV
        </a>
      </div>
      <p className="text-xs leading-6 text-muted-foreground">
        CSV includes all stores and dates from this saved forecast. Estimates
        are not guarantees. Future opening/promotion values remain unknown
        unless explicitly supported.
      </p>
      <label className="flex flex-wrap items-center gap-3 text-sm">
        Store view
        <select
          aria-label="Forecast store view"
          value={store}
          className="rounded-md border border-slate-500 bg-card px-3 py-2"
          onChange={(event) => setStore(event.target.value)}
        >
          <option value="all">All forecast stores</option>
          {forecast.request.store_ids.map((id) => (
            <option key={id} value={id}>
              Store #{id}
            </option>
          ))}
        </select>
      </label>
      {resource.state === "loading" ? (
        <MetricCard
          label="Saved predictions"
          state="loading"
          description="Reading saved values; no new inference or fitting."
        />
      ) : resource.state === "error" ? (
        <ErrorBanner
          title="Saved forecast unavailable"
          message={resource.message}
          onRetry={refresh}
        />
      ) : (
        <ForecastDetail
          key={`${forecast.forecast_id}-${store}`}
          forecast={forecast}
          view={resource.data}
        />
      )}
      <details className="rounded-lg border border-border bg-card px-4">
        <summary className="text-sm">Source and prediction notes</summary>
        <ul className="list-disc space-y-2 pb-4 pl-5 text-xs leading-6 text-muted-foreground">
          {forecast.warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}
