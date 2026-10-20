"use client";

import { useCallback, useEffect, useState } from "react";
import type { z } from "zod";
import { apiRequest } from "./transport";

export type Resource<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "error"; message: string };

/** Abort obsolete reads, validate JSON, and expose explicit retry without stale success values. */
export function useApiResource<T>(
  path: string,
  schema: z.ZodType<T>,
): { resource: Resource<T>; refresh: () => void } {
  const [current, setCurrent] = useState<{
    path: string;
    resource: Resource<T>;
  }>({ path, resource: { state: "loading" } });
  const [revision, setRevision] = useState(0);
  const refresh = useCallback((): void => {
    setCurrent({ path, resource: { state: "loading" } });
    setRevision((value) => value + 1);
  }, [path]);
  useEffect(() => {
    const controller = new AbortController();
    apiRequest(path, schema, { signal: controller.signal }).then(
      (data) => {
        if (!controller.signal.aborted)
          setCurrent({ path, resource: { state: "ready", data } });
      },
      (reason: unknown) => {
        if (!controller.signal.aborted)
          setCurrent({
            path,
            resource: {
              state: "error",
              message:
                reason instanceof Error
                  ? reason.message
                  : "The API is unavailable.",
            },
          });
      },
    );
    return (): void => controller.abort();
  }, [path, schema, revision]);
  // A different store query must not briefly display selectable results from an older query.
  return {
    resource: current.path === path ? current.resource : { state: "loading" },
    refresh,
  };
}
