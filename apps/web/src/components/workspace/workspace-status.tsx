"use client";

import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import { useWorkspace } from "./workspace-provider";

/** Compact dataset, model and API indicators deliberately report separate readiness facts. */
export function WorkspaceStatus(): React.JSX.Element {
  const { dataset, active, health, refresh } = useWorkspace();
  const apiLabel =
    health.state === "loading"
      ? "Checking API connection…"
      : health.state === "error"
        ? "API offline or unavailable"
        : "API connected";
  return (
    <header
      aria-label="Workspace status"
      className="flex min-h-20 flex-wrap items-center justify-between gap-4 border-b border-border bg-card px-4 py-4 md:px-8"
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
        <span>
          <span className="text-muted-foreground">Dataset as-of </span>
          <strong className="font-semibold">
            {dataset.state === "loading"
              ? "Checking…"
              : dataset.state === "error"
                ? "Unavailable"
                : dataset.data.latest
                  ? formatDate(dataset.data.latest.available_through)
                  : "No data"}
          </strong>
        </span>
        <span className="inline-flex items-center gap-2">
          <span
            aria-hidden="true"
            className={`h-2 w-2 rounded-full ${active.state === "ready" && active.data.active_model_version_id ? "bg-teal" : "bg-slate-400"}`}
          />
          <span>
            {active.state === "loading"
              ? "Checking model…"
              : active.state === "error"
                ? "Model unavailable"
                : active.data.active_model_version_id
                  ? "Active model"
                  : "No model"}
          </span>
        </span>
        <span
          role="status"
          aria-live="polite"
          className={
            health.state === "error" ? "text-red-800" : "text-muted-foreground"
          }
        >
          {apiLabel}
        </span>
      </div>
      <Button variant="outline" size="sm" onClick={refresh}>
        Refresh status
      </Button>
    </header>
  );
}
