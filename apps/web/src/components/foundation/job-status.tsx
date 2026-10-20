import type { TrainingJob } from "@/lib/api/training";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "./error-banner";

/** Job completion is distinct from model activation; show actual stages, never invented percentages. */
export function JobStatus({
  job,
  loading = false,
  error,
}: {
  job: TrainingJob | null;
  loading?: boolean;
  error?: string;
}): React.JSX.Element {
  if (loading)
    return (
      <div role="status" aria-label="Loading training status">
        <Skeleton className="h-16 w-full" />
      </div>
    );
  if (error)
    return <ErrorBanner title="Job status unavailable" message={error} />;
  if (!job)
    return (
      <p className="text-sm text-muted-foreground">No training job selected.</p>
    );
  return (
    <div
      role="status"
      aria-live="polite"
      className="space-y-2 rounded-lg border border-border bg-background p-4"
    >
      <Badge
        className={
          job.state === "failed"
            ? "border-red-200 bg-red-50 text-red-900"
            : job.state === "succeeded"
              ? "border-teal-200 bg-teal-50 text-teal-900"
              : ""
        }
      >
        {job.state}
      </Badge>
      <p className="text-sm font-medium">
        Job: {job.state} · {job.stage}
      </p>
      <p className="text-sm leading-6 text-muted-foreground">{job.message}</p>
      <p className="text-xs text-muted-foreground">
        Attempt {job.attempt_count} of {job.max_attempts}. Training success and
        model approval are separate.
      </p>
    </div>
  );
}
