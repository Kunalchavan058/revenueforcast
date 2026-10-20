"use client";

import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { storePageSchema } from "@/lib/api/catalog";
import { useApiResource } from "@/lib/api/use-api-resource";
import { ErrorBanner } from "./error-banner";

const PAGE_SIZE = 25;

/** Bounded server-side store search; unsupported stores stay explicitly unavailable for forecasts. */
export function StorePicker({
  value,
  onChange,
  disabled = false,
}: {
  value: number | null;
  onChange: (storeId: number | null) => void;
  disabled?: boolean;
}): React.JSX.Element {
  const id = useId();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = new URLSearchParams({
    search,
    page: String(page),
    page_size: String(PAGE_SIZE),
  });
  const { resource, refresh } = useApiResource(
    `/stores?${query}`,
    storePageSchema,
  );
  const data = resource.state === "ready" ? resource.data : null;
  return (
    <fieldset disabled={disabled} className="space-y-4">
      <legend className="mb-2 text-sm font-semibold">Store</legend>
      <div className="space-y-2">
        <label htmlFor={`${id}-search`} className="text-sm">
          Search store ID
        </label>
        <Input
          id={`${id}-search`}
          inputMode="numeric"
          type="search"
          value={search}
          maxLength={20}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />
      </div>
      {resource.state === "loading" && (
        <div role="status" aria-label="Loading stores">
          <Skeleton className="h-11 w-full" />
        </div>
      )}
      {resource.state === "error" && (
        <ErrorBanner
          title="Stores unavailable"
          message={resource.message}
          onRetry={refresh}
        />
      )}
      {data &&
        (data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {search
              ? "No stores match this search."
              : "No stores imported yet."}
          </p>
        ) : (
          <div className="space-y-2">
            <label htmlFor={`${id}-store`} className="text-sm">
              Choose store
            </label>
            <select
              id={`${id}-store`}
              value={value ?? ""}
              aria-describedby={`${id}-help`}
              onChange={(event) =>
                onChange(event.target.value ? Number(event.target.value) : null)
              }
              className="w-full rounded-md border border-slate-500 bg-card px-3 py-2 text-sm"
            >
              <option value="">Select a store</option>
              {value !== null &&
                !data.items.some((item) => item.store_id === value) && (
                  <option value={value}>Selected store #{value}</option>
                )}
              {data.items.map((item) => (
                <option
                  key={item.store_id}
                  value={item.store_id}
                  disabled={!item.forecast_supported}
                >
                  Store #{item.store_id}
                  {item.forecast_supported ? "" : " — outside model coverage"}
                </option>
              ))}
            </select>
            <p
              id={`${id}-help`}
              className="text-xs leading-5 text-muted-foreground"
            >
              Only stores supported by the active model can be selected for
              forecasting.
            </p>
          </div>
        ))}
      {data && data.total > PAGE_SIZE && (
        <div className="flex flex-wrap items-center gap-4">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous stores
          </Button>
          <span className="text-xs">
            Page {page} of {Math.ceil(data.total / PAGE_SIZE)}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page * PAGE_SIZE >= data.total}
            onClick={() => setPage(page + 1)}
          >
            Next stores
          </Button>
        </div>
      )}
    </fieldset>
  );
}
