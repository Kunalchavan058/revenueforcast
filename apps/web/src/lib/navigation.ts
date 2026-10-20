import type { IconName } from "@/components/foundation/icon";

export const navigation: readonly {
  href: string;
  label: string;
  icon: IconName;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
}[] = [
  {
    href: "/",
    label: "Overview",
    icon: "overview",
    description: "Source coverage, model readiness and your next step.",
    emptyTitle: "",
    emptyDescription: "",
  },
  {
    href: "/forecasts",
    label: "Forecasts",
    icon: "forecasts",
    description:
      "Daily sales estimates with a clear store, cutoff and horizon.",
    emptyTitle: "",
    emptyDescription:
      "Generate cutoff-safe predictions from the active saved model.",
  },
  {
    href: "/model-studio",
    label: "Model Studio",
    icon: "models",
    description: "Train a candidate while your active model keeps serving.",
    emptyTitle: "",
    emptyDescription: "",
  },
  {
    href: "/experiments",
    label: "Experiments",
    icon: "experiments",
    description: "Compare measured results on the same historical windows.",
    emptyTitle: "Experiment browsing is not available yet",
    emptyDescription:
      "Training records real metrics in MLflow. This page will make those runs and comparable validation windows easier to inspect; no sample scores are shown.",
  },
  {
    href: "/feature-explorer",
    label: "Feature Explorer",
    icon: "features",
    description: "Understand what the model can know at forecast time.",
    emptyTitle: "Feature explanations are coming to this workspace",
    emptyDescription:
      "The feature registry API already documents inputs and availability. Its interactive explorer will be built separately. Customer counts are excluded from V1 predictors.",
  },
  {
    href: "/data-settings",
    label: "Data & Settings",
    icon: "settings",
    description:
      "Dataset provenance, observed dates and local training settings.",
    emptyTitle: "Data management controls are not available yet",
    emptyDescription:
      "Use the documented operator commands to import validated observations and configure the standalone worker. Import and schedule forms are planned for a later phase.",
  },
];
