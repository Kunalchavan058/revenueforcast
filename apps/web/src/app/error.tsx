"use client";

import { ErrorBanner } from "@/components/foundation/error-banner";

/** Avoid leaking framework/server diagnostics; keep a local retry available. */
export default function WorkspaceError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.JSX.Element {
  return (
    <ErrorBanner
      title="This workspace could not load"
      message="Try again. Your saved datasets and active model have not been changed by this page."
      onRetry={reset}
    />
  );
}
