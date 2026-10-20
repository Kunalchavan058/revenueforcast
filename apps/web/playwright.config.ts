import { defineConfig, devices } from "@playwright/test";

/** Allow isolated browser servers alongside an operator's existing dev processes. */
function serverPort(name: string, fallback: number): number {
  const port = Number(process.env[name] || fallback);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error(`${name} must be an integer from 1024 to 65535`);
  }
  return port;
}
const webPort = serverPort("PLAYWRIGHT_WEB_PORT", 3000);
const apiPort = serverPort("PLAYWRIGHT_API_PORT", 8000);
const webUrl = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  expect: { timeout: process.env.PLAYWRIGHT_DEV === "1" ? 15000 : 5000 },
  workers: 1,
  use: {
    baseURL: webUrl,
    ...devices["Desktop Chrome"],
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
  },
  webServer: [
    {
      command: `uv run --locked python -m uvicorn main:app --app-dir services/api --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../..",
      url: `http://127.0.0.1:${apiPort}/api/v1/health`,
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_API === "1",
      timeout: 60000,
    },
    {
      command: `npm run ${process.env.PLAYWRIGHT_DEV === "1" ? "dev" : "start"} -- --hostname 127.0.0.1 --port ${webPort}`,
      url: webUrl,
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_WEB === "1",
      timeout: process.env.PLAYWRIGHT_DEV === "1" ? 180000 : 60000,
    },
  ],
});
