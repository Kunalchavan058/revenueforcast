"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { fetchHealth } from "@/lib/api/client";

type ConnectionState = "loading" | "connected" | "offline";

/** Show a real liveness request, including initial, offline, and retry states. */
export function ApiHealth(): React.JSX.Element {
  const [state, setState] = useState<ConnectionState>("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal).then(
      () => {
        if (!controller.signal.aborted) setState("connected");
      },
      () => {
        if (!controller.signal.aborted) setState("offline");
      },
    );
    return (): void => controller.abort();
  }, [attempt]);

  const labels: Record<ConnectionState, string> = {
    loading: "Checking API connection…",
    connected: "API connected",
    offline: "API offline or unavailable",
  };

  function retry(): void {
    setState("loading");
    setAttempt((value) => value + 1);
  }

  return (
    <section
      aria-labelledby="connection-heading"
      className="rounded-xl border border-border bg-card p-6"
    >
      <h2 id="connection-heading" className="text-lg font-semibold">
        Local API
      </h2>
      <p
        role="status"
        aria-live="polite"
        className="my-3 text-muted-foreground"
      >
        {labels[state]}
      </p>
      {state === "connected" && (
        <p className="text-sm text-muted-foreground">
          The service is responding. Model availability is checked separately.
        </p>
      )}
      {state === "offline" && (
        <p className="mb-4 text-sm text-muted-foreground">
          Start the local API, then check the connection again.
        </p>
      )}
      <Button
        variant="outline"
        onClick={retry}
        disabled={state === "loading"}
        className="mt-4"
      >
        Check again
      </Button>
    </section>
  );
}
