"use client";

import { useId } from "react";
import { z } from "zod";
import { Input } from "@/components/ui/input";

export type DateRange = { start: string; end: string };

/** Source business dates remain YYYY-MM-DD strings; no implicit timezone conversion or date swapping. */
export function DateRangePicker({
  value,
  onChange,
  min,
  max,
  disabled = false,
}: {
  value: DateRange;
  onChange: (range: DateRange) => void;
  min?: string;
  max?: string;
  disabled?: boolean;
}): React.JSX.Element {
  const id = useId();
  const supplied = [value.start, value.end].filter(Boolean);
  const error = supplied.some((date) => !z.iso.date().safeParse(date).success)
    ? "Enter valid calendar dates."
    : value.start && value.end && value.start > value.end
      ? "End date must be on or after start date."
      : supplied.some((date) => (min && date < min) || (max && date > max))
        ? "Choose dates within the available data range."
        : null;
  return (
    <fieldset disabled={disabled} className="space-y-4">
      <legend className="mb-2 text-sm font-semibold">Date range</legend>
      <div className="grid gap-4 sm:grid-cols-2">
        {(["start", "end"] as const).map((field) => (
          <div key={field} className="space-y-2">
            <label htmlFor={`${id}-${field}`} className="text-sm">
              {field === "start" ? "Start date" : "End date"}
            </label>
            <Input
              id={`${id}-${field}`}
              type="date"
              value={value[field]}
              min={min}
              max={max}
              aria-invalid={!!error}
              aria-describedby={`${id}-help`}
              onChange={(event) =>
                onChange({ ...value, [field]: event.target.value })
              }
            />
          </div>
        ))}
      </div>
      <p
        id={`${id}-help`}
        role={error ? "alert" : undefined}
        className={
          error ? "text-sm text-red-800" : "text-xs text-muted-foreground"
        }
      >
        {error ??
          "Choose business dates. Forecast cutoff and horizon are separate forecast inputs."}
      </p>
    </fieldset>
  );
}
