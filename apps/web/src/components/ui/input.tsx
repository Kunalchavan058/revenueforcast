import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Native input retains browser keyboard behavior and explicit external labels. */
export function Input({
  className,
  ...props
}: ComponentProps<"input">): React.JSX.Element {
  return (
    <input
      data-slot="input"
      className={cn(
        "w-full rounded-md border border-slate-500 bg-card px-3 py-2 text-sm disabled:bg-muted",
        className,
      )}
      {...props}
    />
  );
}
