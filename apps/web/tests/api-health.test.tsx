import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ApiHealth } from "@/components/api-health";

afterEach(() => vi.unstubAllGlobals());

test("shows loading while the API has not responded", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
  render(<ApiHealth />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "Checking API connection",
  );
});

test("shows connected only for a valid API response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      Response.json({
        status: "ok",
        service: "retailforecast-api",
        api_version: "v1",
      }),
    ),
  );
  render(<ApiHealth />);
  expect(await screen.findByText("API connected")).toBeInTheDocument();
});

test.each([
  ["HTTP failure", () => Promise.resolve(new Response("", { status: 503 }))],
  ["invalid schema", () => Promise.resolve(Response.json({ status: "ok" }))],
  ["network failure", () => Promise.reject(new Error("offline"))],
])("shows offline for %s", async (_name, response) => {
  vi.stubGlobal("fetch", vi.fn(response));
  render(<ApiHealth />);
  expect(
    await screen.findByText("API offline or unavailable"),
  ).toBeInTheDocument();
});
