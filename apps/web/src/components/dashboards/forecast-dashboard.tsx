"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/foundation/page-header";
import { EmptyState } from "@/components/foundation/empty-state";
import { ErrorBanner } from "@/components/foundation/error-banner";
import { MetricCard } from "@/components/foundation/metric-card";
import { DataFreshnessNotice } from "@/components/foundation/data-freshness-notice";
import { ForecastStorePicker } from "@/components/foundation/multi-store-picker";
import {
  forecastOptionsSchema,
  generateForecast,
  DEFAULT_HORIZON,
  DEFAULT_STORE_SELECTION,
  type ForecastOptions,
  type ForecastResponse,
} from "@/lib/api/dashboards";
import { useApiResource } from "@/lib/api/use-api-resource";
import { cutoffBounds } from "@/lib/dashboard-dates";
import { formatDate } from "@/lib/format";
import { ForecastResults } from "./forecast-results";

/** Explicit saved-model inference form; mounting and changing inputs never send a training request. */
function ForecastForm({
  options,
}: {
  options: ForecastOptions;
}): React.JSX.Element {
  const defaults = options.stores
    .slice(0, DEFAULT_STORE_SELECTION)
    .map((store) => store.store_id);
  const [stores, setStores] = useState(defaults);
  const [cutoff, setCutoff] = useState(
    () => cutoffBounds(options, defaults)?.max ?? "",
  );
  const [horizon, setHorizon] = useState(DEFAULT_HORIZON);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const bounds = cutoffBounds(options, stores);
  const valid =
    !!bounds &&
    cutoff >= bounds.min &&
    cutoff <= bounds.max &&
    horizon >= 1 &&
    horizon <= options.max_horizon &&
    stores.length > 0;
  const pending =
    result &&
    (JSON.stringify(result.request.store_ids) !== JSON.stringify(stores) ||
      result.request.cutoff_date !== cutoff ||
      result.request.horizon_days !== horizon);
  async function generate(): Promise<void> {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await generateForecast({
          store_ids: stores,
          cutoff_date: cutoff,
          horizon_days: horizon,
        }),
      );
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The forecast request could not finish. Check the API and input history.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <DataFreshnessNotice date={options.coverage?.observed_through} />
      <p className="break-all text-xs leading-6 text-muted-foreground">
        Current saved model: {options.model?.version_id} ·{" "}
        {options.model?.algorithm} · trained through{" "}
        {formatDate(options.model?.trained_until)}. No fitting is performed by
        this page.
      </p>
      <Card className="p-6">
        <form
          className="space-y-6"
          onSubmit={(event) => {
            event.preventDefault();
            void generate();
          }}
        >
          <div className="grid gap-8 lg:grid-cols-2">
            <ForecastStorePicker
              items={options.stores.map((store) => store.store_id)}
              value={stores}
              disabled={busy}
              limit={options.max_stores}
              onChange={(selected) => {
                setStores(selected);
                const next = cutoffBounds(options, selected);
                if (next && (cutoff < next.min || cutoff > next.max))
                  setCutoff(next.max);
              }}
            />
            <div className="space-y-4">
              <div className="space-y-2">
                <label
                  htmlFor="forecast-cutoff"
                  className="text-sm font-semibold"
                >
                  As-of date
                </label>
                <Input
                  id="forecast-cutoff"
                  type="date"
                  value={cutoff}
                  min={bounds?.min}
                  max={bounds?.max}
                  disabled={busy || !bounds}
                  onChange={(event) => setCutoff(event.target.value)}
                  aria-describedby="forecast-cutoff-help"
                />
                <p
                  id="forecast-cutoff-help"
                  className="text-xs leading-5 text-muted-foreground"
                >
                  {bounds
                    ? `Selected-store input coverage and fit date allow ${formatDate(bounds.min)} – ${formatDate(bounds.max)}. Sales availability delay: ${options.sales_delay_days} days.`
                    : "Select supported stores with overlapping observed history after model training."}
                </p>
              </div>
              <div className="space-y-2">
                <label
                  htmlFor="forecast-horizon"
                  className="text-sm font-semibold"
                >
                  Horizon (days)
                </label>
                <select
                  id="forecast-horizon"
                  className="block w-full rounded-md border border-slate-500 bg-card px-3 py-2 text-sm"
                  value={horizon}
                  disabled={busy}
                  onChange={(event) => setHorizon(Number(event.target.value))}
                >
                  {Array.from({ length: options.max_horizon }, (_, index) => (
                    <option key={index + 1} value={index + 1}>
                      {index + 1} {index === 0 ? "day" : "days"}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={busy || !valid}>
              {busy ? "Generating forecast…" : "Generate Forecast"}
            </Button>
            <p className="text-xs text-muted-foreground">
              Reuses the active saved model. Predictions are estimates, not
              guaranteed revenue.
            </p>
          </div>
          {busy && (
            <p role="status" className="text-sm">
              Generating daily predictions from cutoff-safe history…
            </p>
          )}
          {!valid && (
            <p className="text-sm text-red-800">
              Choose at least one supported store, a covered as-of date and a
              1–48 day horizon.
            </p>
          )}
        </form>
      </Card>
      {error && (
        <ErrorBanner title="Forecast could not be generated" message={error} />
      )}
      {pending && (
        <p className="text-sm text-muted-foreground">
          Inputs changed. Results below still describe the saved forecast;
          generate again to use these inputs.
        </p>
      )}
      {result ? (
        <ForecastResults key={result.forecast_id} forecast={result} />
      ) : (
        !busy &&
        !error && (
          <Card>
            <EmptyState
              title="Ready to generate a forecast"
              description="Choose your stores, historical as-of date and horizon. Predictions appear only after the saved model returns a real response."
            />
          </Card>
        )
      )}
    </>
  );
}

/** Explain absent models/history before exposing any prediction action. */
export function ForecastDashboard(): React.JSX.Element {
  const { resource, refresh } = useApiResource(
    "/forecasts/options",
    forecastOptionsSchema,
  );
  return (
    <>
      <PageHeader
        title="Forecasts"
        description="Generate daily store sales estimates from a saved model and a fixed observed-data cutoff."
      />
      {resource.state === "loading" ? (
        <MetricCard
          state="loading"
          label="Forecast setup"
          description="Checking saved model and observed input coverage…"
        />
      ) : resource.state === "error" ? (
        <ErrorBanner
          title="Forecast setup unavailable"
          message={resource.message}
          onRetry={refresh}
        />
      ) : !resource.data.model ? (
        <Card>
          <EmptyState
            title="No active model"
            description="Forecasts need a validated saved model. Train the first model in Model Studio; this page will never start training for you."
            action={
              <Button asChild>
                <Link href="/model-studio">Train first model</Link>
              </Button>
            }
          />
        </Card>
      ) : !resource.data.coverage || !resource.data.stores.length ? (
        <Card>
          <EmptyState
            title="No compatible observed history"
            description="Import validated sales for the active model's supported stores. An unlabeled competition test file is not actual sales history."
          />
        </Card>
      ) : (
        <ForecastForm
          key={resource.data.model.version_id}
          options={resource.data}
        />
      )}
    </>
  );
}
