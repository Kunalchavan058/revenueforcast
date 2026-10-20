import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { TrainingControl } from "@/components/training-control";

const MODEL_ID = "11111111-1111-4111-8111-111111111111";
const JOB_ID = "22222222-2222-4222-8222-222222222222";

afterEach(() => vi.unstubAllGlobals());

/** Return only transport fixtures; component tests never fit or claim measured forecasts. */
function job(state: "queued" | "skipped" = "queued"): object {
  return {
    id: JOB_ID,
    algorithm: "auto",
    state,
    stage: state === "queued" ? "queued" : "complete",
    message:
      state === "queued"
        ? "Waiting for the standalone worker"
        : "skipped: no new labeled observations",
    attempt_count: 0,
    max_attempts: 2,
    model_version_id: null,
    worker_required: true,
  };
}

test("does not claim forecasts are ready while model availability is loading", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
  render(<TrainingControl />);
  expect(screen.getByText("Checking active model…")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Train first model" }),
  ).toBeDisabled();
  expect(
    screen.queryByText(/active model remains available/),
  ).not.toBeInTheDocument();
});

test("offers initial training, enqueues only algorithm and displays durable queued state", async () => {
  const fetcher = vi
    .fn<(url: string, options?: RequestInit) => Promise<Response>>()
    .mockImplementation((url: string) =>
      Promise.resolve(
        Response.json(
          url.endsWith("/models/active")
            ? { active_model_version_id: null, generation: 0 }
            : job(),
        ),
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  render(<TrainingControl />);
  expect(await screen.findByText(/No active model/)).toHaveTextContent(
    "Forecasts are unavailable",
  );
  fireEvent.click(screen.getByRole("button", { name: "Train first model" }));
  expect(await screen.findByText("Job: queued · queued")).toBeInTheDocument();
  expect(
    screen.getByText("Waiting for the standalone worker"),
  ).toBeInTheDocument();
  const call = fetcher.mock.calls.find(([url]) =>
    url.endsWith("/training-jobs"),
  );
  expect(call?.[1]?.body).toBe(JSON.stringify({ algorithm: "auto" }));
  expect(new Headers(call?.[1]?.headers).get("Idempotency-Key")).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "Train first model" }),
  ).toBeDisabled();
});

test("keeps incumbent availability separate from an unchanged-data skip", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation((url: string) =>
        Promise.resolve(
          Response.json(
            url.endsWith("/models/active")
              ? { active_model_version_id: MODEL_ID, generation: 2 }
              : job("skipped"),
          ),
        ),
      ),
  );
  render(<TrainingControl />);
  expect(
    await screen.findByText(/active model remains available/),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Train a candidate" }));
  expect(
    await screen.findByText("skipped: no new labeled observations"),
  ).toBeInTheDocument();
  expect(screen.getByText("Job: skipped · complete")).toBeInTheDocument();
});

test("shows an honest unavailable-model state on invalid or offline responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json({ status: "ok" })),
  );
  render(<TrainingControl />);
  expect(
    await screen.findByText("Cannot check model availability."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Train first model" }),
  ).toBeDisabled();
});

test("shows an actionable import error without creating a fake successful job", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith("/models/active")
          ? Response.json({ active_model_version_id: null, generation: 0 })
          : Response.json(
              {
                error: {
                  code: "dataset_required",
                  message:
                    "Import validated labeled sales before requesting training",
                },
              },
              { status: 503 },
            ),
      ),
    ),
  );
  render(<TrainingControl />);
  await screen.findByText(/No active model/);
  fireEvent.click(screen.getByRole("button", { name: "Train first model" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Import validated labeled sales",
  );
  expect(screen.queryByText(/Job:/)).not.toBeInTheDocument();
});
