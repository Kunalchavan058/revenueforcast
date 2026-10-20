import type { ReactNode } from "react";

/** Native disclosure keeps important forecasting assumptions usable without hover. */
export function MethodologyHint({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}): React.JSX.Element {
  return (
    <details className="rounded-lg border border-border bg-card px-4">
      <summary className="text-sm font-medium">{title}</summary>
      <div className="pb-4 text-sm leading-6 text-muted-foreground">
        {children}
      </div>
    </details>
  );
}
