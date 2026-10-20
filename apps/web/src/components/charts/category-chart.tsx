"use client";

import { useEffect, useRef } from "react";
import { init, use as registerECharts } from "echarts/core";
import { BarChart } from "echarts/charts";
import {
  AriaComponent,
  GridComponent,
  TooltipComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { Card } from "@/components/ui/card";
import { formatSales } from "@/lib/format";

registerECharts([
  BarChart,
  AriaComponent,
  GridComponent,
  TooltipComponent,
  SVGRenderer,
]);
export type CategoryValue = {
  label: string;
  value: number | null;
  detail: string;
};

/** Bounded observed-sales comparisons retain a readable table and explicit denominator context. */
export default function CategoryChart({
  title,
  description,
  values,
}: {
  title: string;
  description: string;
  values: readonly CategoryValue[];
}): React.JSX.Element {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current || !values.some((row) => row.value !== null)) return;
    const chart = init(container.current, undefined, { renderer: "svg" });
    chart.setOption({
      animation: false,
      aria: { enabled: true, description },
      grid: { left: 64, right: 16, top: 48, bottom: 48 },
      tooltip: {
        trigger: "axis",
        confine: true,
        valueFormatter: (value: unknown): string =>
          typeof value === "number" ? formatSales(value) : "Not observed",
      },
      xAxis: {
        type: "category",
        data: values.map((row) => row.label),
        axisLabel: { color: "#546174", hideOverlap: true },
      },
      yAxis: {
        type: "value",
        name: "Sales units",
        axisLabel: { color: "#546174" },
      },
      series: [
        {
          type: "bar",
          name: title,
          data: values.map((row) => row.value),
          itemStyle: { color: "#244dcc", borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 36,
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return (): void => {
      observer.disconnect();
      chart.dispose();
    };
  }, [values, title, description]);
  return (
    <Card className="min-w-0 p-6">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        {description}
      </p>
      <div
        ref={container}
        role="img"
        aria-label={description}
        className="h-64 w-full"
      />
      <details>
        <summary className="text-sm">View {title.toLowerCase()} data</summary>
        <div
          role="region"
          aria-label={`${title} table`}
          tabIndex={0}
          className="overflow-x-auto"
        >
          <table className="w-full text-left text-xs">
            <caption className="sr-only">{title}, source Sales units</caption>
            <thead>
              <tr>
                <th scope="col" className="p-2">
                  Group
                </th>
                <th scope="col" className="p-2">
                  Observed sales
                </th>
                <th scope="col" className="p-2">
                  Coverage
                </th>
              </tr>
            </thead>
            <tbody>
              {values.map((row) => (
                <tr key={row.label} className="border-t border-border">
                  <th scope="row" className="p-2 font-normal">
                    {row.label}
                  </th>
                  <td className="p-2">{formatSales(row.value)}</td>
                  <td className="p-2">{row.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  );
}
