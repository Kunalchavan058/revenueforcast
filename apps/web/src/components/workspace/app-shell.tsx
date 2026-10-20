"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Icon } from "@/components/foundation/icon";
import { navigation } from "@/lib/navigation";
import { WorkspaceProvider } from "./workspace-provider";
import { WorkspaceStatus } from "./workspace-status";

/** Stable desktop sidebar and wrapping mobile navigation share one keyboard-accessible link set. */
export function AppShell({
  children,
}: {
  children: ReactNode;
}): React.JSX.Element {
  const pathname = usePathname();
  return (
    <WorkspaceProvider>
      <a
        href="#main-content"
        className="fixed left-4 top-4 z-50 -translate-y-32 rounded bg-primary px-4 py-3 text-sm text-white focus:translate-y-0"
      >
        Skip to content
      </a>
      <div className="min-h-screen lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="border-b border-border bg-card lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-b-0 lg:border-r">
          <Link
            href="/"
            aria-label="RetailForecast AI overview"
            className="flex min-h-20 items-center gap-3 px-6 py-4"
          >
            <span className="rounded-lg bg-primary p-2 text-white">
              <Icon name="forecasts" width={24} height={24} />
            </span>
            <span className="text-lg font-semibold tracking-tight">
              RetailForecast{" "}
              <span className="ml-1 text-xs font-medium text-muted-foreground">
                AI
              </span>
            </span>
          </Link>
          <div className="px-4 pb-4 lg:px-4 lg:pt-8">
            <p className="mb-4 hidden px-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground lg:block">
              Planning workspace
            </p>
            <nav
              aria-label="Main navigation"
              className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-1"
            >
              {navigation.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={pathname === item.href ? "page" : undefined}
                  className={`flex min-h-11 items-center gap-3 rounded-lg px-3 py-3 text-sm ${pathname === item.href ? "bg-blue-50 font-semibold text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                >
                  <Icon name={item.icon} className="shrink-0" />
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="mt-auto hidden border-t border-border p-6 lg:block">
            <p className="text-xs font-semibold">Historical workspace</p>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              Observed sales inform forecasts. A saved model is reused for each
              request.
            </p>
          </div>
        </aside>
        <div className="min-w-0">
          <WorkspaceStatus />
          <main
            id="main-content"
            tabIndex={-1}
            className="mx-auto max-w-[1440px] space-y-8 px-4 py-8 outline-none md:px-8 lg:py-10"
          >
            {children}
          </main>
          <footer className="mx-auto flex max-w-[1440px] flex-wrap justify-between gap-4 px-4 pb-8 text-xs leading-5 text-muted-foreground md:px-8">
            <span>RetailForecast AI · Historical sales workspace</span>
            <span>
              Estimates, not guaranteed revenue. Source currency unspecified.
            </span>
          </footer>
        </div>
      </div>
    </WorkspaceProvider>
  );
}
