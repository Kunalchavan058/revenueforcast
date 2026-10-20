import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Icon, type IconName } from "./icon";

/** A real measured/display value with separate unavailable states; absence is never zero. */
export function MetricCard({
  label,
  value,
  description,
  state = "ready",
  icon = "database",
}: {
  label: string;
  value?: string | null;
  description: string;
  state?: "ready" | "loading" | "empty" | "error";
  icon?: IconName;
}): React.JSX.Element {
  return (
    <Card className="p-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm font-medium text-muted-foreground">{label}</h2>
        <Icon name={icon} className="text-muted-foreground" />
      </div>
      {state === "loading" ? (
        <div role="status" aria-label={`Loading ${label}`} className="my-4">
          <Skeleton className="h-8 w-32" />
        </div>
      ) : (
        <p className="my-3 break-words text-2xl font-semibold tracking-tight tabular-nums">
          {state === "error"
            ? "Unavailable"
            : state === "empty" || value == null
              ? "Not available"
              : value}
        </p>
      )}
      <p className="text-xs leading-5 text-muted-foreground">{description}</p>
    </Card>
  );
}
