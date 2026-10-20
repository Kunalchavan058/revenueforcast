import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** Static shadcn/ui loading placeholder; the parent supplies an accessible status label. */
export function Skeleton({
  className,
  ...props
}: ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      aria-hidden="true"
      data-slot="skeleton"
      className={cn("rounded bg-muted", className)}
      {...props}
    />
  );
}
