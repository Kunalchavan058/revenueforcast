"use client";

import { createContext, useContext, type ReactNode } from "react";
import { datasetStatusSchema, type DatasetStatus } from "@/lib/api/catalog";
import { healthResponseSchema, type HealthResponse } from "@/lib/api/schemas";
import { activeSlotSchema, type ActiveSlot } from "@/lib/api/training";
import { useApiResource, type Resource } from "@/lib/api/use-api-resource";

type Workspace = {
  dataset: Resource<DatasetStatus>;
  active: Resource<ActiveSlot>;
  health: Resource<HealthResponse>;
  refresh: () => void;
};
const WorkspaceContext = createContext<Workspace | null>(null);

/** Independent read-only status calls let liveness succeed even when storage/model reads fail. */
export function WorkspaceProvider({
  children,
}: {
  children: ReactNode;
}): React.JSX.Element {
  const dataset = useApiResource("/datasets/status", datasetStatusSchema);
  const active = useApiResource("/models/active", activeSlotSchema);
  const health = useApiResource("/health", healthResponseSchema);
  function refresh(): void {
    dataset.refresh();
    active.refresh();
    health.refresh();
  }
  return (
    <WorkspaceContext.Provider
      value={{
        dataset: dataset.resource,
        active: active.resource,
        health: health.resource,
        refresh,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

/** Consume the shared status snapshot; no page invents its own model-ready flag. */
export function useWorkspace(): Workspace {
  const value = useContext(WorkspaceContext);
  if (!value)
    throw new Error("Workspace components require WorkspaceProvider.");
  return value;
}
