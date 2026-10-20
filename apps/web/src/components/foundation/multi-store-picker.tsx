"use client";

import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { storePageSchema } from "@/lib/api/catalog";
import { MAX_SELECTED_STORES } from "@/lib/api/dashboards";
import { useApiResource } from "@/lib/api/use-api-resource";
import { ErrorBanner } from "./error-banner";

type Props = {
  value: readonly number[];
  onChange: (value: number[]) => void;
  disabled?: boolean;
  limit?: number;
};

/** One checkbox contract for business stores and the smaller supported forecasting cohort. */
function Checklist({
  items,
  value,
  onChange,
  disabled,
  limit = MAX_SELECTED_STORES,
}: Props & { items: readonly number[] }): React.JSX.Element {
  return (
    <div className="grid max-h-44 grid-cols-2 gap-2 overflow-y-auto rounded-md border border-border p-2 sm:grid-cols-3">
      {items.map((id) => (
        <label
          key={id}
          className="flex min-h-11 items-center gap-2 rounded px-2 text-sm hover:bg-muted"
        >
          <input
            type="checkbox"
            className="h-4 w-4 accent-primary"
            checked={value.includes(id)}
            disabled={
              disabled || (!value.includes(id) && value.length >= limit)
            }
            onChange={() =>
              onChange(
                value.includes(id)
                  ? value.filter((selected) => selected !== id)
                  : [...value, id].sort((a, b) => a - b),
              )
            }
          />
          Store #{id}
        </label>
      ))}
    </div>
  );
}

/** All historical stores may be explored; unsupported forecasting cohorts are not excluded here. */
export function HistoricalStorePicker({
  sourceId,
  ...props
}: Props & { sourceId: string }): React.JSX.Element {
  const id = useId();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({
    dataset_version_id: sourceId,
    search,
    page: String(page),
    page_size: "25",
  });
  const { resource, refresh } = useApiResource(
    `/stores?${params}`,
    storePageSchema,
  );
  return (
    <fieldset disabled={props.disabled} className="space-y-3">
      <legend className="mb-2 text-sm font-semibold">
        Stores · {props.value.length} selected
      </legend>
      <label className="sr-only" htmlFor={id}>
        Search historical stores
      </label>
      <Input
        id={id}
        type="search"
        placeholder="Search store ID"
        value={search}
        onChange={(event) => {
          setSearch(event.target.value);
          setPage(1);
        }}
      />
      <p className="text-xs text-muted-foreground">
        Selected:{" "}
        {props.value.length
          ? props.value.map((store) => `#${store}`).join(", ")
          : "None"}
        . Maximum {props.limit ?? MAX_SELECTED_STORES} stores.
      </p>
      {resource.state === "loading" ? (
        <p role="status" className="text-sm">
          Loading stores…
        </p>
      ) : resource.state === "error" ? (
        <ErrorBanner message={resource.message} onRetry={refresh} />
      ) : (
        <>
          <Checklist
            {...props}
            items={resource.data.items.map((store) => store.store_id)}
          />
          {resource.data.items.length === 0 && (
            <p className="text-sm">No matching stores.</p>
          )}
          <div className="flex items-center gap-4">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              Previous stores
            </Button>
            <span className="text-xs">Page {page}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page * 25 >= resource.data.total}
              onClick={() => setPage(page + 1)}
            >
              Next stores
            </Button>
          </div>
        </>
      )}
    </fieldset>
  );
}

/** Forecast choices come only from the active saved model with actual input history. */
export function ForecastStorePicker({
  items,
  ...props
}: Props & { items: readonly number[] }): React.JSX.Element {
  return (
    <fieldset disabled={props.disabled} className="space-y-3">
      <legend className="mb-2 text-sm font-semibold">
        Forecast stores · {props.value.length} selected
      </legend>
      <Checklist {...props} items={items} />
      <p className="text-xs text-muted-foreground">
        Only supported stores with historical inputs. Select up to{" "}
        {props.limit ?? MAX_SELECTED_STORES}.
      </p>
    </fieldset>
  );
}
