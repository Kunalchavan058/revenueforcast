import { formatDate } from "@/lib/format";
import { Icon } from "./icon";

/** Expose observed-date freshness, never substitute import time or today's clock. */
export function DataFreshnessNotice({
  date,
  state = "ready",
}: {
  date?: string | null;
  state?: "loading" | "ready" | "error";
}): React.JSX.Element {
  return (
    <aside
      aria-label="Data freshness"
      className="flex gap-3 rounded-lg border border-blue-200 bg-blue-50/60 p-4 text-blue-950"
    >
      <Icon name="info" className="mt-0.5 shrink-0" />
      <div>
        <p className="text-sm font-medium">
          {state === "loading"
            ? "Checking the dataset’s observed dates…"
            : state === "error"
              ? "Dataset freshness is unavailable"
              : date
                ? `Historical actuals through ${formatDate(date)}`
                : "No dataset imported"}
        </p>
        <p className="mt-1 text-xs leading-5">
          The Rossmann dataset is historical. It is not a live sales feed.{" "}
          {state === "error"
            ? "Reconnect to verify the source before forecasting."
            : "Forecasts are estimates after an explicit cutoff; new sales require a validated import."}
        </p>
      </div>
    </aside>
  );
}
