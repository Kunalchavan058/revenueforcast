import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/workspace/app-shell";

export const metadata: Metadata = {
  title: "RetailForecast AI",
  description: "Historical retail sales and transparent saved-model forecasts",
};

/** Provide the shared document shell without remote font or cloud requests. */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>): React.JSX.Element {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
