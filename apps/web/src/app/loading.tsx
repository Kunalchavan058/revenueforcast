import { Skeleton } from "@/components/ui/skeleton";

/** A stable content placeholder while a route loads; shell status remains independent. */
export default function Loading(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading workspace" className="space-y-8">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-6 w-3/4" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
