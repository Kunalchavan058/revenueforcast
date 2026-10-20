import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  coverageResponseSchema,
  forecastOptionsSchema,
  forecastResponseSchema,
} from "../src/lib/api/dashboards";

test.setTimeout(120000);

/** Wait for real status reads before saving representative interface screenshots. */
async function expectWorkspaceReady(
  page: import("@playwright/test").Page,
): Promise<void> {
  const status = page.getByRole("banner", { name: "Workspace status" });
  await expect(
    status.getByText("API connected", { exact: true }),
  ).toBeVisible();
  await expect(status).not.toContainText("Checking…");
  await expect(status).not.toContainText("Checking model…");
  await expect(status).not.toContainText("Unavailable");
  await expect(status).not.toContainText("Model unavailable");
}

test("overview reads real metadata, is accessible and has no invented forecast", async ({
  page,
}) => {
  await page.goto("/");
  await expectWorkspaceReady(page);
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }).getByRole("link"),
  ).toHaveCount(6);
  const coverage = coverageResponseSchema.parse(
    await (await page.request.get("/api/v1/history/coverage")).json(),
  ).coverage;
  if (coverage) {
    await expect(
      page.getByRole("heading", { name: "Actual sales over time" }),
    ).toBeVisible();
    await expect(page.getByLabel("Data freshness")).toContainText(
      "not a live sales feed",
    );
    await expect(
      page.getByRole("link", { name: "Download observed CSV" }),
    ).toBeVisible();
    await expect(page.locator('[data-chart="sales"] svg')).toBeVisible();
  } else
    await expect(
      page.getByText("No historical sales imported", { exact: true }),
    ).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: test.info().outputPath("overview-desktop.png"),
    fullPage: true,
  });
});

test("status loading, offline and retry remain separate from model readiness", async ({
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
  const status = page.getByRole("banner", { name: "Workspace status" });
  await expect(status.getByRole("status")).toContainText(
    "Checking API connection",
  );
  finishRequest?.();
  await expect(status.getByRole("status")).toHaveText(
    "API offline or unavailable",
  );
  await page.unroute("**/api/v1/health");
  await status.getByRole("button", { name: "Refresh status" }).click();
  await expect(status.getByRole("status")).toHaveText("API connected");
});

test("first-model onboarding queues work without claiming forecasts are ready", async ({
  page,
}) => {
  await page.route("**/api/v1/models/active", (route) =>
    route.fulfill({ json: { active_model_version_id: null, generation: 0 } }),
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
  await page.goto("/model-studio");
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

test("all navigation destinations work and planned features are honest empty states", async ({
  page,
}) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  for (const label of [
    "Forecasts",
    "Model Studio",
    "Experiments",
    "Feature Explorer",
    "Data & Settings",
    "Overview",
  ]) {
    await nav.getByRole("link", { name: label, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: label, exact: true }),
    ).toBeVisible();
    await expect(
      nav.getByRole("link", { name: label, exact: true }),
    ).toHaveAttribute("aria-current", "page");
    if (!["Model Studio", "Overview", "Forecasts"].includes(label))
      await expect(page.getByText("Browser workflow planned")).toBeVisible();
  }
});

test("mobile navigation fits the viewport and remains accessible", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expectWorkspaceReady(page);
  const source = coverageResponseSchema.parse(
    await (await page.request.get("/api/v1/history/coverage")).json(),
  ).coverage;
  if (source) {
    await expect(
      page.getByRole("heading", { name: "Weekday pattern", exact: true }),
    ).toBeVisible();
    await expect(page.locator("main [role=img] svg")).toHaveCount(3);
  }

  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: test.info().outputPath("overview-mobile.png"),
    fullPage: true,
  });
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Model Studio" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Model Studio", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
});

test("keyboard skip link reaches content and methodology disclosures open", async ({
  page,
}) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  const disclosure = page.getByText("What does dataset as-of mean?", {
    exact: true,
  });
  await disclosure.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.locator("details").filter({ has: disclosure }),
  ).toHaveAttribute("open", "");
});

test("real saved-model forecast responds to selected stores without any training request", async ({
  page,
}) => {
  const trainingCalls: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("training-jobs"))
      trainingCalls.push(request.url());
  });
  await page.goto("/forecasts");
  const setupResponse = await page.request.get("/api/v1/forecasts/options");
  expect(setupResponse.ok()).toBe(true);
  const setup = forecastOptionsSchema.parse(await setupResponse.json());
  if (!setup.model) {
    await expect(
      page.getByRole("link", { name: "Train first model" }),
    ).toBeVisible();
    expect(trainingCalls).toEqual([]);
    return;
  }
  if (!setup.stores.length) {
    await expect(
      page.getByText("No compatible observed history", { exact: true }),
    ).toBeVisible();
    expect(trainingCalls).toEqual([]);
    return;
  }
  const selected = setup.stores.slice(0, 3).map((store) => store.store_id);
  if (selected.length > 1) {
    await page
      .getByRole("checkbox", { name: `Store #${selected.at(-1)}`, exact: true })
      .uncheck();
    selected.pop();
  }
  await page.getByLabel("Horizon (days)").selectOption("7");
  const responsePromise = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/forecasts" &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generate Forecast", exact: true })
    .click();
  const response = await responsePromise;
  expect(response.status()).toBe(201);
  const forecast = forecastResponseSchema.parse(await response.json());
  expect(forecast.request.store_ids).toEqual(selected);
  expect(forecast.points).toHaveLength(selected.length * 7);
  await expect(
    page.getByRole("heading", { name: "Saved predictions", exact: true }),
  ).toBeVisible();
  await expect(page.locator('[data-chart="sales"] svg')).toBeVisible();
  await expect(
    page.getByText(`Last observed date: ${forecast.data.actual_data_cutoff}`, {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: test.info().outputPath("forecast-desktop.png"),
    fullPage: true,
  });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download forecast CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain(forecast.forecast_id);
  await page.getByLabel("Prediction results period").selectOption("weekly");
  await expect(
    page.getByRole("columnheader", { name: "Covered week dates" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: test.info().outputPath("forecast-mobile.png"),
    fullPage: true,
  });
  expect(trainingCalls).toEqual([]);
});
