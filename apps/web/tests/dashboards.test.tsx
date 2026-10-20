import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Overview } from "@/components/workspace/overview";
import { ForecastDashboard } from "@/components/dashboards/forecast-dashboard";
import { cutoffBounds, initialHistoryRange } from "@/lib/dashboard-dates";
import type {
  ForecastInput,
  ForecastResponse,
  HistoryQuery,
} from "@/lib/api/dashboards";
import {
  coverage,
  options,
  SOURCE_ID,
  MODEL_ID,
  historyFixture,
  forecastFixture,
  viewFixture,
} from "./dashboard-fixtures";

vi.mock("@/components/charts/sales-chart", () => ({
  default: () => <div data-testid="sales-renderer" />,
}));
vi.mock("@/components/charts/category-chart", () => ({
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));
afterEach(() => vi.unstubAllGlobals());

/** Resolve only explicit transport fixtures and record every request; unexpected paths fail. */
function transport(): ReturnType<
  typeof vi.fn<(url: string, init?: RequestInit) => Promise<Response>>
> {
  let saved: ForecastResponse | null = null;
  return vi
    .fn<(url: string, init?: RequestInit) => Promise<Response>>()
    .mockImplementation(async (url, init) => {
      if (url.endsWith("/history/coverage")) return Response.json({ coverage });
      if (url.endsWith("/forecasts/options")) return Response.json(options);
      if (url.includes("/stores?"))
        return Response.json({
          dataset_version_id: SOURCE_ID,
          source_available_through: "2015-07-31",
          page: 1,
          page_size: 25,
          total: 2,
          items: [1, 2].map((store_id) => ({
            store_id,
            store_type: null,
            assortment: null,
            forecast_supported: true,
          })),
        });
      if (url.endsWith("/forecasts") && init?.method === "POST") {
        saved = forecastFixture(JSON.parse(String(init.body)) as ForecastInput);
        return Response.json(saved, { status: 201 });
      }
      if (url.includes("/view") && saved)
        return Response.json(viewFixture(saved));
      if (url.includes("/history/summary?")) {
        const params = new URL(url, "http://test").searchParams;
        const query: HistoryQuery = {
          dataset_version_id: params.get("dataset_version_id")!,
          store_ids: params.getAll("store_ids").map(Number),
          start_date: params.get("start_date")!,
          end_date: params.get("end_date")!,
          frequency: params.get("frequency") as HistoryQuery["frequency"],
        };
        return Response.json(historyFixture(query));
      }
      throw new Error(`Unexpected test request ${url}`);
    });
}

test("overview applies selected stores and historical dates to real report requests and CSV", async () => {
  const fetcher = transport();
  vi.stubGlobal("fetch", fetcher);
  render(<Overview />);
  await screen.findByRole("checkbox", { name: "Store #2" });
  fireEvent.click(screen.getByRole("checkbox", { name: "Store #2" }));
  fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  await waitFor(() =>
    expect(
      fetcher.mock.calls.some(([url]) => {
        const p = new URL(url, "http://test");
        return (
          p.pathname.endsWith("/history/summary") &&
          p.searchParams.getAll("store_ids").join() === "1"
        );
      }),
    ).toBe(true),
  );
  expect(screen.getByLabelText("Start date")).toHaveValue("2015-07-04");
  expect(screen.getByLabelText("End date")).toHaveValue("2015-07-31");
  expect(
    screen
      .getByRole("link", { name: "Download observed CSV" })
      .getAttribute("href"),
  ).toContain("store_ids=1");
  expect(
    fetcher.mock.calls.some(([url]) => url.includes("training-jobs")),
  ).toBe(false);
});

test("forecast selection/horizon alter the POST, saved response renders, and no training fires", async () => {
  const fetcher = transport();
  vi.stubGlobal("fetch", fetcher);
  render(<ForecastDashboard />);
  await screen.findByRole("checkbox", { name: "Store #2" });
  expect(fetcher.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
    false,
  );
  fireEvent.click(screen.getByRole("checkbox", { name: "Store #2" }));
  fireEvent.change(screen.getByLabelText("Horizon (days)"), {
    target: { value: "1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Generate Forecast" }));
  await screen.findByRole("heading", { name: "Forecast results" });
  await screen.findByRole("heading", {
    name: "Saved predictions",
  });
  const request = fetcher.mock.calls.find(
    ([url, init]) => url.endsWith("/forecasts") && init?.method === "POST",
  );
  expect(JSON.parse(String(request?.[1]?.body))).toEqual({
    store_ids: [1],
    cutoff_date: "2015-07-31",
    horizon_days: 1,
  });
  expect(
    screen.getByRole("cell", { name: "12.50 Sales units" }),
  ).toBeInTheDocument();
  expect(screen.getByText(new RegExp(`Model ${MODEL_ID}`))).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Download forecast CSV" }),
  ).toHaveAttribute("href", expect.stringContaining("/download.csv"));
  expect(
    fetcher.mock.calls.some(
      ([url]) => url.includes("training-jobs") || url.includes("/activate"),
    ),
  ).toBe(false);
  await waitFor(() =>
    expect(
      fetcher.mock.calls.some(([url]) => url.includes("/history/summary?")),
    ).toBe(true),
  );
  const historyCalls = fetcher.mock.calls.filter(([url]) =>
    url.includes("/history/summary?"),
  );
  expect(
    new URL(historyCalls[0]![0], "http://test").searchParams.get("end_date"),
  ).toBe("2015-07-31");
  fireEvent.change(screen.getByLabelText("Prediction results period"), {
    target: { value: "weekly" },
  });
  expect(
    screen.getByRole("columnheader", { name: "Covered week dates" }),
  ).toBeInTheDocument();
});

test("missing model links to Model Studio without a hidden training call", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      Response.json({ ...options, model: null, coverage: null, stores: [] }),
    );
  vi.stubGlobal("fetch", fetcher);
  render(<ForecastDashboard />);
  expect(
    await screen.findByRole("link", { name: "Train first model" }),
  ).toHaveAttribute("href", "/model-studio");
  expect(
    screen.queryByRole("button", { name: "Generate Forecast" }),
  ).not.toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

test("forecast failures are explained without fabricated results or automatic retraining", async () => {
  const original = transport();
  const fetcher = vi
    .fn<(url: string, init?: RequestInit) => Promise<Response>>()
    .mockImplementation((url, init) =>
      init?.method === "POST"
        ? Promise.resolve(
            Response.json(
              { error: { message: "No observed history for this store" } },
              { status: 422 },
            ),
          )
        : original(url, init),
    );
  vi.stubGlobal("fetch", fetcher);
  render(<ForecastDashboard />);
  await screen.findByRole("button", { name: "Generate Forecast" });
  fireEvent.click(screen.getByRole("button", { name: "Generate Forecast" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "No observed history for this store",
  );
  expect(
    screen.queryByRole("heading", { name: "Forecast results" }),
  ).not.toBeInTheDocument();
  expect(
    fetcher.mock.calls.some(([url]) => url.includes("training-jobs")),
  ).toBe(false);
});

test("source-date defaults and selected-store cutoff overlap include availability delay", () => {
  expect(initialHistoryRange(coverage)).toEqual({
    start: "2015-07-04",
    end: "2015-07-31",
  });
  expect(
    cutoffBounds(
      {
        ...options,
        sales_delay_days: 2,
        stores: [
          options.stores[0]!,
          {
            store_id: 2,
            observed_from: "2015-07-20",
            observed_through: "2015-07-28",
          },
        ],
      },
      [1, 2],
    ),
  ).toEqual({ min: "2015-07-22", max: "2015-07-30" });
  expect(cutoffBounds(options, [])).toBeNull();
  expect(cutoffBounds(options, [999])).toBeNull();
});
