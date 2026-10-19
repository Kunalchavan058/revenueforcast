import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RetailForecast AI",
  description: "Local-first retail forecasting — application skeleton",
};

/** Provide the shared document shell without remote font or cloud requests. */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>): React.JSX.Element {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
