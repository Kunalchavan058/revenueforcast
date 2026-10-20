import type { NextConfig } from "next";

/** Keep browser requests same-origin; infrastructure URLs stay server-side. */
const config: NextConfig = {
  // An isolated dev output avoids taking the operator's existing Next lock.
  distDir: process.env.PLAYWRIGHT_DEV === "1" ? ".next-browser" : ".next",
  async rewrites() {
    const apiBaseUrl = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiBaseUrl.replace(/\/$/, "")}/api/v1/:path*`,
      },
    ];
  },
};

export default config;
