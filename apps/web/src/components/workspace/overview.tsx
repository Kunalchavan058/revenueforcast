"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/foundation/page-header";
import { DataFreshnessNotice } from "@/components/foundation/data-freshness-notice";
import {
  DateRangePicker,
  type DateRange,
} from "@/components/foundation/date-range-picker";
import { HistoricalStorePicker } from "@/components/foundation/multi-store-picker";
import { EmptyState } from "@/components/foundation/empty-state";
import { ErrorBanner } from "@/components/foundation/error-banner";
import { MetricCard } from "@/components/foundation/metric-card";
import { MethodologyHint } from "@/components/foundation/methodology-hint";
import { OverviewReport } from "@/components/dashboards/overview-report";
import {
  MAX_HISTORY_DAYS,
  coverageResponseSchema,
  historySummarySchema,
  historyPath,
  type HistoryQuery,
  type SourceCoverage,
} from "@/lib/api/dashboards";
import { useApiResource } from "@/lib/api/use-api-resource";
import { initialHistoryRange } from "@/lib/dashboard-dates";
import { formatDate } from "@/lib/format";

/** Bind default filters to the observed source, never the operator's current date. */
function HistoricalOverview({
  coverage,
}: {
  coverage: SourceCoverage;
}): React.JSX.Element {
  const [stores, setStores] = useState<number[]>(coverage.default_store_ids);
  const [range, setRange] = useState<DateRange>(() =>
    initialHistoryRange(coverage),
  );
  const [applied, setApplied] = useState<HistoryQuery>({
    dataset_version_id: coverage.dataset_version_id,
    store_ids: coverage.default_store_ids,
    start_date: range.start,
    end_date: range.end,
    frequency: "day",
  });
  const { resource, refresh } = useApiResource(
    historyPath(applied),
    historySummarySchema,
  );
  const valid =
    stores.length > 0 &&
    range.start >= coverage.observed_from &&
    range.end <= coverage.observed_through &&
    range.start <= range.end &&
    !!range.start &&
    !!range.end &&
    (Date.parse(range.end) - Date.parse(range.start)) / 86400000 <
      MAX_HISTORY_DAYS;
  const pending =
    JSON.stringify(stores) !== JSON.stringify(applied.store_ids) ||
    range.start !== applied.start_date ||
    range.end !== applied.end_date;
  return (
    <>
      <DataFreshnessNotice date={coverage.observed_through} />
      <p className="text-xs text-muted-foreground">
        Available history: {formatDate(coverage.observed_from)} –{" "}
        {formatDate(coverage.observed_through)} · {coverage.store_count} stores
        in this source.
      </p>
      <Card className="p-6">
        <form
          className="space-y-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid)
              setApplied({
                ...applied,
                store_ids: stores,
                start_date: range.start,
                end_date: range.end,
              });
          }}
        >
          <div className="grid gap-8 lg:grid-cols-2">
            <HistoricalStorePicker
              sourceId={coverage.dataset_version_id}
              value={stores}
              onChange={setStores}
            />
            <DateRangePicker
              value={range}
              onChange={setRange}
              min={coverage.observed_from}
              max={coverage.observed_through}
            />
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={!valid}>
              Apply filters
            </Button>
            <a
              href={`/api/v1${historyPath(applied, true)}`}
              className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-medium"
            >
              Download observed CSV
            </a>
            <label className="flex items-center gap-2 text-sm">
              Period
              <select
                aria-label="Actual sales period"
                value={applied.frequency}
                onChange={(event) =>
                  setApplied({
                    ...applied,
                    frequency: event.target.value as HistoryQuery["frequency"],
                  })
                }
                className="rounded-md border border-slate-500 bg-card px-3 py-2"
              >
                <option value="day">Daily</option>
                <option value="week">Weekly</option>
                <option value="month">Monthly</option>
              </select>
            </label>
          </div>
          {pending && (
            <p className="text-sm text-muted-foreground">
              Filters changed. Apply filters to update the results and export.
            </p>
          )}
          {!valid && (
            <p className="text-sm text-red-800">
              Choose at least one store and an ordered interval within coverage
              (maximum 1,096 days).
            </p>
          )}
        </form>
      </Card>
      <p className="text-xs text-muted-foreground">
        Showing {applied.store_ids.length} selected stores ·{" "}
        {formatDate(applied.start_date)} – {formatDate(applied.end_date)}.
      </p>
      {resource.state === "loading" ? (
        <MetricCard
          state="loading"
          label="Observed sales"
          description="Computing from imported observations…"
        />
      ) : resource.state === "error" ? (
        <ErrorBanner
          title="History could not load"
          message={resource.message}
          onRetry={refresh}
        />
      ) : (
        <OverviewReport report={resource.data} />
      )}
      <MethodologyHint title="What does dataset as-of mean?">
        It is the latest observed sales date, not today or the import timestamp.
        Reporting describes historical outcomes and never supplies future
        outcomes to model features. Missing store-days are excluded from means
        and kept distinct from zero sales.
      </MethodologyHint>
    </>
  );
}

/** Functional business history, independent of whether any model has been trained. */
export function Overview(): React.JSX.Element {
  const { resource, refresh } = useApiResource(
    "/history/coverage",
    coverageResponseSchema,
  );
  return (
    <>
      <PageHeader
        title="Overview"
        description="Explore observed sales, store comparisons and weekday patterns for an explicit historical period."
      />
      {resource.state === "loading" ? (
        <MetricCard
          state="loading"
          label="Historical coverage"
          description="Reading observed dataset dates…"
        />
      ) : resource.state === "error" ? (
        <ErrorBanner
          title="Historical coverage unavailable"
          message={resource.message}
          onRetry={refresh}
        />
      ) : resource.data.coverage ? (
        <HistoricalOverview
          key={resource.data.coverage.dataset_version_id}
          coverage={resource.data.coverage}
        />
      ) : (
        <Card>
          <EmptyState
            title="No historical sales imported"
            description="Import validated observed sales before exploring business totals. No current dates or sample sales are substituted."
            action={
              <a href="/data-settings" className="font-semibold text-primary">
                Review data setup
              </a>
            }
          />
        </Card>
      )}
    </>
  );
}
