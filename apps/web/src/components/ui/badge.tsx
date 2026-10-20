import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Quiet textual status badge; meaning never depends only on its color. */
export function Badge({
  className,
  ...props
}: ComponentProps<"span">): React.JSX.Element {
  return (
    <span
      data-slot="badge"
      className={cn(
        "inline-flex items-center gap-2 rounded-md border border-border px-2 py-1 text-xs font-medium",
        className,
      )}
      {...props}
    />
  );
}
