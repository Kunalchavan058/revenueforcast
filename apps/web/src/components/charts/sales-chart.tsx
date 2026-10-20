"use client";

import { useEffect, useRef } from "react";
import { init, use as registerECharts } from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  AriaComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { formatSales } from "@/lib/format";
import type { SalesPoint } from "./types";

registerECharts([
  LineChart,
  AriaComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
  SVGRenderer,
]);

/** Lazy SVG chart; actual and predicted series never connect across missing observations. */
export default function SalesChart({
  points,
  description,
  lastObservedDate,
}: {
  points: readonly SalesPoint[];
  description: string;
  lastObservedDate?: string;
}): React.JSX.Element {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const chart = init(container.current, undefined, { renderer: "svg" });
    chart.setOption({
      animation: false,
      aria: { enabled: true, description },
      grid: { left: 72, right: 24, top: 48, bottom: 48 },
      tooltip: {
        trigger: "axis",
        confine: true,
        valueFormatter: (value: unknown): string =>
          typeof value === "number" ? formatSales(value) : "Not observed",
      },
      xAxis: {
        type: "category",
        data: points.map((point) => point.date),
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#8290a3" } },
        axisLabel: { color: "#546174" },
      },
      yAxis: {
        type: "value",
        name: "Sales units",
        min: 0,
        axisLabel: { color: "#546174" },
        splitLine: { lineStyle: { color: "#eef2f7" } },
      },
      series: [
        {
          name: "Historical actuals",
          type: "line",
          data: points.map((point) => point.actual),
          connectNulls: false,
          showSymbol:
            points.filter((point) => point.actual !== null).length === 1,
          markLine: lastObservedDate
            ? {
                silent: true,
                symbol: ["none", "none"],
                lineStyle: { color: "#546174", type: "dotted", width: 2 },
                label: {
                  formatter: `Last observed date: ${lastObservedDate}`,
                  position: "insideEndTop",
                },
                data: [{ xAxis: lastObservedDate }],
              }
            : undefined,
          lineStyle: { color: "#244dcc", width: 2, type: "solid" },
          itemStyle: { color: "#244dcc" },
        },
        {
          name: "Predicted sales",
          type: "line",
          data: points.map((point) => point.predicted),
          connectNulls: false,
          showSymbol:
            points.filter((point) => point.predicted !== null).length === 1,
          symbolSize: 7,
          lineStyle: { color: "#087983", width: 2, type: "dashed" },
          itemStyle: { color: "#087983" },
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return (): void => {
      observer.disconnect();
      chart.dispose();
    };
  }, [points, description, lastObservedDate]);
  return (
    <div
      data-chart="sales"
      ref={container}
      role="img"
      aria-label={description}
      className="h-80 w-full"
    />
  );
}
