import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Local shadcn/ui card surface; semantics are supplied by its owning section. */
export function Card({
  className,
  ...props
}: ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="card"
      className={cn("rounded-xl border border-border bg-card", className)}
      {...props}
    />
  );
}
