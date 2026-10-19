import { expect, test } from "@playwright/test";

test("home page connects through the real API proxy", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "RetailForecast AI", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("API connected");
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
