import { Button } from "@/components/ui/button";
import { Icon } from "./icon";

/** An actionable request failure; preserve a textual explanation and keyboard retry. */
export function ErrorBanner({
  title = "We couldn’t load this information",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}): React.JSX.Element {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-start gap-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-900"
    >
      <Icon name="info" className="mt-1 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{title}</p>
        <p className="mt-1 text-sm leading-6">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
