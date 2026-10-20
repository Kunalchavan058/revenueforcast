import { TrainingControl } from "@/components/training-control";
import { PageHeader } from "@/components/foundation/page-header";
import { MethodologyHint } from "@/components/foundation/methodology-hint";

/** Preserve Phase 11's real training action; detailed version/comparison pages remain deferred. */
export default function ModelStudio(): React.JSX.Element {
  return (
    <>
      <PageHeader
        title="Model Studio"
        description="Train a candidate while your active model keeps serving. Algorithm selection stays simple."
      />
      <div className="max-w-3xl space-y-8">
        <TrainingControl />
        <MethodologyHint title="When should I retrain?">
          Only new validated labeled sales beyond the consumed data watermark
          make retraining eligible. Static Kaggle data does not update
          automatically. A successful job creates a candidate; shared-window
          checks separately decide whether it becomes active.
        </MethodologyHint>
      </div>
    </>
  );
}
