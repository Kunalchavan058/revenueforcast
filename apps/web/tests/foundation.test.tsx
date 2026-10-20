import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { PageHeader } from "@/components/foundation/page-header";
import { MetricCard } from "@/components/foundation/metric-card";
import { EmptyState } from "@/components/foundation/empty-state";
import { ErrorBanner } from "@/components/foundation/error-banner";
import { DataFreshnessNotice } from "@/components/foundation/data-freshness-notice";
import { DateRangePicker } from "@/components/foundation/date-range-picker";
import { StorePicker } from "@/components/foundation/store-picker";
import { JobStatus } from "@/components/foundation/job-status";
import { ChartShell } from "@/components/foundation/chart-shell";
import { MethodologyHint } from "@/components/foundation/methodology-hint";
import { formatDate, formatCount, formatSales } from "@/lib/format";
import { apiRequest } from "@/lib/api/transport";
import { healthResponseSchema } from "@/lib/api/schemas";
import { datasetStatusSchema } from "@/lib/api/catalog";
import type { TrainingJob } from "@/lib/api/training";

// Tiny transport/component fixtures never appear as production metrics or charts.
vi.mock("@/components/charts/sales-chart", () => ({
  default: () => <div data-testid="sales-renderer" />,
}));
afterEach(() => vi.unstubAllGlobals());

test("page headers keep a single task title and optional real action", () => {
  render(
    <PageHeader
      title="Forecasts"
      description="Choose a historical cutoff."
      actions={<button>Retry</button>}
    />,
  );
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "Forecasts",
  );
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test.each(["loading", "empty", "error"] as const)(
  "metric card shows %s without inventing zero or a trend",
  (state) => {
    render(
      <MetricCard
        label="Rows"
        description="Imported labels only."
        state={state}
      />,
    );
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(
      state === "loading"
        ? screen.getByRole("status", { name: "Loading Rows" })
        : screen.getByText(state === "error" ? "Unavailable" : "Not available"),
    ).toBeInTheDocument();
  },
);

test("empty state explains missing data and exposes its next action", () => {
  render(
    <EmptyState
      title="No dataset"
      description="Import validated actual sales."
      action={<a href="/data-settings">Review data</a>}
    />,
  );
  expect(screen.getByText("No dataset")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Review data" })).toHaveAttribute(
    "href",
    "/data-settings",
  );
});

test("error banner announces a failure and supports retry", () => {
  const retry = vi.fn();
  render(<ErrorBanner message="Database is unavailable." onRetry={retry} />);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Database is unavailable.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(retry).toHaveBeenCalledOnce();
});

test.each(["loading", "ready", "error"] as const)(
  "freshness %s never substitutes today's date",
  (state) => {
    render(<DataFreshnessNotice date={null} state={state} />);
    expect(screen.getByLabelText("Data freshness")).toHaveTextContent(
      "not a live sales feed",
    );
    expect(
      screen.queryByText(/Historical actuals through/),
    ).not.toBeInTheDocument();
  },
);

test("freshness uses observed business date rather than import time", () => {
  render(<DataFreshnessNotice date="2015-07-31" />);
  expect(
    screen.getByText("Historical actuals through 31 Jul 2015"),
  ).toBeInTheDocument();
});

test("date picker empty state preserves explicit labels and source-date strings", () => {
  const change = vi.fn();
  render(<DateRangePicker value={{ start: "", end: "" }} onChange={change} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Start date"), {
    target: { value: "2015-07-31" },
  });
  expect(change).toHaveBeenCalledWith({ start: "2015-07-31", end: "" });
});

test("date picker reports reversed and unavailable ranges without silently swapping", () => {
  const { rerender } = render(
    <DateRangePicker
      value={{ start: "2015-08-01", end: "2015-07-31" }}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "End date must be on or after start date",
  );
  expect(screen.getByLabelText("Start date")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  rerender(
    <DateRangePicker
      value={{ start: "2015-08-01", end: "2015-08-02" }}
      max="2015-07-31"
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("available data range");
});

test("store picker announces loading before any option can be selected", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
  render(<StorePicker value={null} onChange={vi.fn()} />);
  expect(
    screen.getByRole("status", { name: "Loading stores" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});

const emptyStores = {
  dataset_version_id: null,
  source_available_through: null,
  page: 1,
  page_size: 25,
  total: 0,
  items: [],
};

test("store picker distinguishes an empty import from unavailable data", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(emptyStores)));
  render(<StorePicker value={null} onChange={vi.fn()} />);
  expect(
    await screen.findByText("No stores imported yet."),
  ).toBeInTheDocument();
});

test("store picker retries errors and marks unsupported stores explicitly", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response("", { status: 503 }))
    .mockResolvedValueOnce(
      Response.json({
        ...emptyStores,
        total: 2,
        items: [
          {
            store_id: 1,
            store_type: "a",
            assortment: "a",
            forecast_supported: true,
          },
          {
            store_id: 2,
            store_type: null,
            assortment: null,
            forecast_supported: false,
          },
        ],
      }),
    );
  vi.stubGlobal("fetch", fetcher);
  const change = vi.fn();
  render(<StorePicker value={null} onChange={change} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Stores unavailable",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  const select = await screen.findByRole("combobox", { name: "Choose store" });
  expect(
    within(select).getByRole("option", { name: /Store #2/ }),
  ).toBeDisabled();
  fireEvent.change(select, { target: { value: "1" } });
  expect(change).toHaveBeenCalledWith(1);
});

test("store search cancels obsolete reads and hides old options immediately", async () => {
  const fetcher = vi
    .fn<(url: string, options?: RequestInit) => Promise<Response>>()
    .mockResolvedValueOnce(
      Response.json({
        ...emptyStores,
        total: 1,
        items: [
          {
            store_id: 1,
            store_type: null,
            assortment: null,
            forecast_supported: true,
          },
        ],
      }),
    )
    .mockImplementation(() => new Promise<Response>(() => {}));
  vi.stubGlobal("fetch", fetcher);
  render(<StorePicker value={null} onChange={vi.fn()} />);
  await screen.findByRole("combobox");
  const firstSignal = fetcher.mock.calls[0]?.[1]?.signal;
  fireEvent.change(screen.getByLabelText("Search store ID"), {
    target: { value: "9" },
  });
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(firstSignal?.aborted).toBe(true);
  expect(fetcher.mock.calls[1]?.[0]).toContain("search=9");
});

test("job status has honest empty/loading/error states", () => {
  const { rerender } = render(<JobStatus job={null} />);
  expect(screen.getByText("No training job selected.")).toBeInTheDocument();
  rerender(<JobStatus job={null} loading />);
  expect(
    screen.getByRole("status", { name: "Loading training status" }),
  ).toBeInTheDocument();
  rerender(<JobStatus job={null} error="Worker status unavailable." />);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Worker status unavailable.",
  );
});

test.each([
  "queued",
  "running",
  "succeeded",
  "failed",
  "skipped",
  "cancelled",
] as const)("job %s is not confused with active model approval", (state) => {
  const job: TrainingJob = {
    id: "22222222-2222-4222-8222-222222222222",
    algorithm: "auto",
    state,
    stage: "complete",
    message: "Recorded job summary",
    attempt_count: 1,
    max_attempts: 2,
    model_version_id: null,
    worker_required: true,
  };
  render(<JobStatus job={job} />);
  expect(screen.getByRole("status")).toHaveTextContent(`Job: ${state}`);
  expect(
    screen.getByText(/Training success and model approval are separate/),
  ).toBeInTheDocument();
});

test("chart has empty/loading/error states without drawing fake series", () => {
  const { rerender } = render(
    <ChartShell title="Sales" description="Historical source units." />,
  );
  expect(screen.getByText("No forecast to display")).toBeInTheDocument();
  expect(screen.getByLabelText("Chart legend")).toHaveTextContent(
    "Historical actuals",
  );
  expect(screen.getByLabelText("Chart legend")).toHaveTextContent(
    "Predicted sales",
  );
  expect(screen.queryByTestId("sales-renderer")).not.toBeInTheDocument();
  rerender(<ChartShell title="Sales" description="Source units." loading />);
  expect(
    screen.getByRole("status", { name: "Loading chart" }),
  ).toBeInTheDocument();
  rerender(
    <ChartShell
      title="Sales"
      description="Source units."
      error="No labeled data."
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("No labeled data.");
});

test("chart validates calendar uniqueness and preserves missing values in its accessible table", async () => {
  const point = { date: "2015-07-31", actual: 0, predicted: null };
  const { rerender } = render(
    <ChartShell
      title="Sales"
      description="Recorded and estimated sales."
      points={[point, point]}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("unique calendar dates");
  rerender(
    <ChartShell
      title="Sales"
      description="Recorded and estimated sales."
      points={[point]}
    />,
  );
  await screen.findByTestId("sales-renderer");
  fireEvent.click(screen.getByText("View chart data table"));
  expect(
    screen.getByRole("cell", { name: "0.00 Sales units" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("cell", { name: "Not available" }),
  ).toBeInTheDocument();
});

test("methodology is a native keyboard disclosure with a plain-language explanation", () => {
  render(
    <MethodologyHint title="Why a cutoff?">
      Future actuals stay outside predictors.
    </MethodologyHint>,
  );
  expect(screen.getByText("Why a cutoff?").tagName).toBe("SUMMARY");
  expect(
    screen.getByText("Future actuals stay outside predictors."),
  ).toBeInTheDocument();
});

test("date/count/sales formatting preserves absence and does not invent currency", () => {
  expect(formatDate("2015-07-31")).toBe("31 Jul 2015");
  expect(formatDate("2015-02-30")).toBe("Not available");
  expect(formatDate(undefined)).toBe("Not available");
  expect(formatCount(1017209)).toBe("1,017,209");
  expect(formatCount(null)).toBe("Not available");
  expect(formatSales(0)).toBe("0.00 Sales units");
  expect(formatSales(null)).toBe("Not available");
  expect(formatSales(12, "EUR")).toBe("€12.00");
});

test("typed transport rejects malformed and unreadable responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(Response.json({ status: "ok" }))
      .mockResolvedValueOnce(new Response("not json", { status: 502 })),
  );
  await expect(apiRequest("/health", healthResponseSchema)).rejects.toThrow(
    "expected contract",
  );
  await expect(apiRequest("/health", healthResponseSchema)).rejects.toThrow(
    "unreadable response",
  );
});

test("catalog schema rejects fabricated calendar dates and negative counts", () => {
  expect(
    datasetStatusSchema.safeParse({
      latest: null,
      active_model_dataset_version_id: null,
      source_kind: "imported_historical_snapshot",
      notice: "No source",
    }).success,
  ).toBe(true);
  expect(
    datasetStatusSchema.safeParse({
      latest: { available_through: "2015-02-30", rows: -1 },
    }).success,
  ).toBe(false);
});
