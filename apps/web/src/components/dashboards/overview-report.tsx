"use client";

import { lazy, Suspense } from "react";
import { ChartShell } from "@/components/foundation/chart-shell";
import { MetricCard } from "@/components/foundation/metric-card";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCount, formatDate, formatSales } from "@/lib/format";
import type { HistorySummary } from "@/lib/api/dashboards";

const CategoryChart = lazy(() => import("@/components/charts/category-chart"));
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Present SQL-computed actual totals; no UI extrapolation or hidden missing-day imputation. */
export function OverviewReport({
  report,
}: {
  report: HistorySummary;
}): React.JSX.Element {
  const actuals = report.series.map((row) => ({
    date: row.covered_from,
    actual: row.sales === null ? null : Number(row.sales),
    predicted: null,
  }));
  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Observed sales"
          value={formatSales(
            report.total_sales === null ? null : Number(report.total_sales),
          )}
          description="Includes known zero-sales and closed days."
        />
        <MetricCard
          label="Selected stores"
          value={formatCount(report.selected_store_count)}
          description={`${formatDate(report.query.start_date)} – ${formatDate(report.query.end_date)}`}
          icon="overview"
        />
        <MetricCard
          label="Observed store-days"
          value={formatCount(report.observed_store_days)}
          description={`${formatCount(report.missing_store_days)} missing of ${formatCount(report.expected_store_days)} expected.`}
        />
        <MetricCard
          label="Closed store-days"
          value={formatCount(report.closed_store_days)}
          description={`${formatCount(report.open_store_days)} open store-days in reported history.`}
          icon="settings"
        />
      </div>
      <ChartShell
        title="Actual sales over time"
        description={`${report.query.frequency === "day" ? "Daily" : report.query.frequency === "week" ? "Monday–Sunday weekly" : "Calendar monthly"} totals from observed store-days only. Partial coverage is listed below.`}
        points={actuals}
        showPredictions={false}
        emptyTitle="No observed sales in this selection"
        emptyDescription="Choose stores and dates with imported labeled observations. Missing observations are not zero-sales days."
      />
      <div className="grid gap-8 xl:grid-cols-2">
        <Suspense fallback={<Skeleton className="h-80 w-full" />}>
          <CategoryChart
            title="Sales by store"
            description="Observed sales totals for the same selected dates; missing days remain excluded."
            values={report.by_store.map((row) => ({
              label: `#${row.store_id}`,
              value: row.sales === null ? null : Number(row.sales),
              detail: `${row.observed_store_days} observed store-days`,
            }))}
          />
        </Suspense>
        <Suspense fallback={<Skeleton className="h-80 w-full" />}>
          <CategoryChart
            title="Weekday pattern"
            description="Mean Sales per observed store-day, including closed-day zeros. Coverage can differ by weekday."
            values={report.weekdays.map((row) => ({
              label: WEEKDAYS[row.weekday - 1]!,
              value: row.mean_sales === null ? null : Number(row.mean_sales),
              detail: `${row.observations} observed store-days`,
            }))}
          />
        </Suspense>
      </div>
      <p className="text-xs leading-6 text-muted-foreground">
        Open/closed figures describe recorded history, not future opening plans.{" "}
        {report.closed_positive_sales_days > 0
          ? `${report.closed_positive_sales_days} recorded closed store-days have positive sales; those source quirks remain in totals.`
          : "Missing dates are counted separately from closed dates."}
      </p>
      <Card className="p-6">
        <h2 className="font-semibold">Period totals and coverage</h2>
        <div
          role="region"
          aria-label="Observed period totals"
          tabIndex={0}
          className="mt-4 max-h-96 overflow-auto"
        >
          <table className="w-full text-left text-sm">
            <caption className="sr-only">
              Observed sales for the exact selected period, in source Sales
              units
            </caption>
            <thead>
              <tr>
                <th scope="col" className="p-3">
                  Covered dates
                </th>
                <th scope="col" className="p-3">
                  Observed sales
                </th>
                <th scope="col" className="p-3">
                  Observed / expected store-days
                </th>
              </tr>
            </thead>
            <tbody>
              {report.series.map((row) => (
                <tr key={row.period_start} className="border-t border-border">
                  <th scope="row" className="p-3 font-normal">
                    {formatDate(row.covered_from)}
                    {row.covered_from !== row.covered_through &&
                      ` – ${formatDate(row.covered_through)}`}
                  </th>
                  <td className="p-3 tabular-nums">
                    {formatSales(row.sales === null ? null : Number(row.sales))}
                  </td>
                  <td className="p-3 tabular-nums">
                    {row.observed_store_days} / {row.expected_store_days}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
