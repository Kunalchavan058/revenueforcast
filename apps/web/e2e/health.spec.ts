import { expect, test } from "@playwright/test";

test("home page connects through the real API proxy", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "RetailForecast AI", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("API connected");
  await expect(
    page.getByRole("button", { name: /Train (first model|a candidate)/ }),
  ).toBeEnabled();
  await expect(page.getByText("Cannot check model availability.")).toHaveCount(
    0,
  );
  await page.screenshot({
    path: test.info().outputPath("home.png"),
    fullPage: true,
  });
  await expect(
    page.getByText("The Rossmann dataset is historical.", { exact: false }),
  ).toBeVisible();
});

test("shows loading, offline and successful retry in the browser", async ({
  page,
}) => {
  let finishRequest: (() => void) | undefined;
  const gate = new Promise<void>((resolve) => {
    finishRequest = resolve;
  });
  await page.route("**/api/v1/health", async (route) => {
    await gate;
    await route.fulfill({ status: 503, body: "Unavailable" });
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText(
    "Checking API connection",
  );
  finishRequest?.();
  await expect(page.getByRole("status")).toHaveText(
    "API offline or unavailable",
  );
  await page.unroute("**/api/v1/health");
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByRole("status")).toHaveText("API connected");
  await page.screenshot({
    path: test.info().outputPath("home.png"),
    fullPage: true,
  });
});

test("first-model onboarding queues work without claiming forecasts are ready", async ({
  page,
}) => {
  await page.route("**/api/v1/models/active", (route) =>
    route.fulfill({
      json: { active_model_version_id: null, generation: 0 },
    }),
  );
  await page.route("**/api/v1/training-jobs", (route) =>
    route.fulfill({
      status: 202,
      json: {
        id: "22222222-2222-4222-8222-222222222222",
        algorithm: "auto",
        state: "queued",
        stage: "queued",
        message: "Waiting for the standalone worker",
        attempt_count: 0,
        max_attempts: 2,
        model_version_id: null,
        worker_required: true,
      },
    }),
  );
  await page.goto("/");
  await expect(page.getByText(/No active model/)).toContainText(
    "Forecasts are unavailable",
  );
  await page.getByRole("button", { name: "Train first model" }).click();
  await expect(page.getByText("Job: queued · queued")).toBeVisible();
  await expect(
    page.getByText("Waiting for the standalone worker", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Train first model" }),
  ).toBeDisabled();
});
