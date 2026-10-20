import Link from "next/link";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/foundation/empty-state";

/** Unknown routes have a useful return path inside the same accessible shell. */
export default function NotFound(): React.JSX.Element {
  return (
    <EmptyState
      title="Workspace not found"
      description="Choose a page from the navigation or return to your overview."
      action={
        <Button asChild>
          <Link href="/">Back to overview</Link>
        </Button>
      }
    />
  );
}
