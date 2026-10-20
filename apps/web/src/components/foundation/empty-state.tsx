import type { ReactNode } from "react";
import { Icon, type IconName } from "./icon";

/** Explain what is absent and the next available action without fabricating content. */
export function EmptyState({
  title,
  description,
  action,
  icon = "forecasts",
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: IconName;
}): React.JSX.Element {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center px-6 py-8 text-center">
      <span className="mb-4 rounded-xl border border-border bg-background p-4 text-muted-foreground">
        <Icon name={icon} width={28} height={28} />
      </span>
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
        {description}
      </p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
