import { render } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import SalesChart from "@/components/charts/sales-chart";

const chart = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}));
vi.mock("echarts/core", () => ({ init: () => chart, use: vi.fn() }));
vi.mock("echarts/charts", () => ({ LineChart: {} }));
vi.mock("echarts/components", () => ({
  AriaComponent: {},
  MarkLineComponent: {},
  GridComponent: {},
  TooltipComponent: {},
}));
vi.mock("echarts/renderers", () => ({ SVGRenderer: {} }));

test("ECharts separates actual/predicted series and disposes observers and the instance", () => {
  const disconnect = vi.fn();
  const observe = vi.fn();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = observe;
      disconnect = disconnect;
    },
  );
  const { unmount } = render(
    <SalesChart
      description="Synthetic component fixture only"
      lastObservedDate="2015-07-31"
      points={[
        { date: "2015-07-31", actual: 3, predicted: null },
        { date: "2015-08-01", actual: null, predicted: 4 },
      ]}
    />,
  );
  const option = chart.setOption.mock.calls[0]?.[0];
  expect(option.series[0]).toMatchObject({
    name: "Historical actuals",
    data: [3, null],
    connectNulls: false,
    lineStyle: { type: "solid" },
  });
  expect(option.series[1]).toMatchObject({
    name: "Predicted sales",
    data: [null, 4],
    connectNulls: false,
    lineStyle: { type: "dashed" },
  });
  expect(option.series[0].markLine.data).toEqual([{ xAxis: "2015-07-31" }]);
  expect(option.series[1].showSymbol).toBe(true);
  expect(option.animation).toBe(false);
  expect(observe).toHaveBeenCalledOnce();
  unmount();
  expect(disconnect).toHaveBeenCalledOnce();
  expect(chart.dispose).toHaveBeenCalledOnce();
  vi.unstubAllGlobals();
});
