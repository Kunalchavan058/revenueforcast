"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  enqueueTraining,
  fetchActiveSlot,
  fetchTrainingJob,
  type ActiveSlot,
  type TrainingAlgorithm,
  type TrainingJob,
} from "@/lib/api/training";

const STATUS_POLL_MS = 5000;
const PENDING_STATES = new Set(["queued", "running"]);

/** Offer first training honestly and keep incumbent availability separate from candidate progress. */
export function TrainingControl(): React.JSX.Element {
  const [active, setActive] = useState<ActiveSlot | "loading" | "offline">(
    "loading",
  );
  const [algorithm, setAlgorithm] = useState<TrainingAlgorithm>("auto");
  const [job, setJob] = useState<TrainingJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const requestKey = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchActiveSlot(controller.signal).then(
      (slot) => {
        if (!controller.signal.aborted) setActive(slot);
      },
      () => {
        if (!controller.signal.aborted) setActive("offline");
      },
    );
    return (): void => controller.abort();
  }, [refresh]);

  const jobId = job?.id;
  const jobState = job?.state;
  useEffect(() => {
    if (!jobId || !jobState || !PENDING_STATES.has(jobState)) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll(): Promise<void> {
      try {
        const next = await fetchTrainingJob(jobId!, controller.signal);
        if (controller.signal.aborted) return;
        setJob(next);
        setError(null);
        if (PENDING_STATES.has(next.state))
          timer = setTimeout(poll, STATUS_POLL_MS);
        else setRefresh((value) => value + 1);
      } catch {
        if (!controller.signal.aborted) {
          setError(
            "Cannot refresh job status. Saved work continues independently of this page.",
          );
          timer = setTimeout(poll, STATUS_POLL_MS);
        }
      }
    }
    // This timer only reads status. The standalone worker owns every training/schedule trigger.
    timer = setTimeout(poll, STATUS_POLL_MS);
    return (): void => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, jobState]);

  async function train(): Promise<void> {
    setSubmitting(true);
    setError(null);
    if (job && !PENDING_STATES.has(job.state)) requestKey.current = null;
    requestKey.current ??= crypto.randomUUID();
    try {
      setJob(await enqueueTraining(algorithm, requestKey.current));
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Training request could not be saved.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const hasActive =
    typeof active === "object" && active.active_model_version_id !== null;
  const busy = submitting || (job !== null && PENDING_STATES.has(job.state));
  return (
    <section
      aria-labelledby="training-heading"
      className="space-y-4 rounded-xl border border-border bg-card p-6"
    >
      <h2 id="training-heading" className="text-lg font-semibold">
        Model training
      </h2>
      {active === "loading" ? (
        <p>Checking active model…</p>
      ) : active === "offline" ? (
        <div>
          <p>Cannot check model availability.</p>
          <Button
            variant="outline"
            onClick={() => {
              setActive("loading");
              setRefresh((value) => value + 1);
            }}
          >
            Retry model check
          </Button>
        </div>
      ) : hasActive ? (
        <p>The active model remains available while a candidate trains.</p>
      ) : (
        <p>
          No active model. Import validated sales, then train your first model.
          Forecasts are unavailable until a validated model becomes active.
        </p>
      )}
      <label className="block space-y-1">
        <span>Training algorithm</span>
        <select
          aria-label="Training algorithm"
          value={algorithm}
          disabled={busy}
          onChange={(event) => {
            setAlgorithm(event.target.value as TrainingAlgorithm);
            requestKey.current = null;
          }}
          className="block rounded border border-border bg-background p-2"
        >
          <option value="auto">Auto</option>
          <option value="xgboost">XGBoost</option>
          <option value="lightgbm">LightGBM</option>
        </select>
      </label>
      <Button
        onClick={() => {
          void train();
        }}
        disabled={busy || typeof active === "string"}
      >
        {submitting
          ? "Saving request…"
          : hasActive
            ? "Train a candidate"
            : "Train first model"}
      </Button>
      <p className="text-sm text-muted-foreground">
        Training and recurring checks require the standalone local worker and an
        awake laptop. Recurring retraining is manual by default. Unchanged
        labeled data is skipped.
      </p>
      {job && (
        <div aria-live="polite" className="space-y-1">
          <p>
            Job: {job.state} · {job.stage}
          </p>
          <p>{job.message}</p>
          <p className="text-sm">
            Attempt {job.attempt_count} of {job.max_attempts}
          </p>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
