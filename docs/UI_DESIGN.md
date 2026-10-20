# UI foundation and information hierarchy

This document records the Phase 12 foundation; Phase 13 functional Overview/Forecast behavior is documented in [DASHBOARDS.md](DASHBOARDS.md).

Phase 12 implements a professional application shell, live readiness metadata and reusable interface components. It does not implement all feature workflows. The interface serves a store operator asking “what data can I use?” and a portfolio reviewer asking “can I trust how this was built?”. Both see the same real state; there is no fabricated demo-metrics mode.

## Read the page in this order

1. Persistent context: **Dataset as-of**, **Active model / No model**, and **API health**. These are independent facts. API liveness does not prove database or model readiness. Refresh status deliberately re-reads each contract; route navigation preserves the shared context.
2. Page title and one plain-language purpose. Primary actions belong here only when their destination works. “Open forecasts” opens the explicitly planned workspace; it does not generate predictions.
3. Data freshness: observed historical business date, not import time or today's date. Missing/offline metadata never falls back to a 2015 date, zero rows, a ready model or a fabricated trend.
4. Task content: observed import metadata on Overview, existing real training controls in Model Studio, and explanatory empty states on unbuilt destinations.
5. Methodology: native disclosures explain cutoff, series labels and model reuse without making the primary task read like an engineering manual.

## Desktop wireframe

```text
+-------------------+--------------------------------------------------------+
| RetailForecast AI | Dataset as-of [API date] | [model] | [API] | Refresh |
|                   +--------------------------------------------------------+
| Overview          | Overview                              Open forecasts  |
| Forecasts         | Plain-language purpose                                |
| Model Studio      | [ Historical source notice / unavailable state ]      |
| Experiments       |                                                        |
| Feature Explorer  | [ Imported rows ] [ Latest actual ] [ Serving version ]|
| Data & Settings   |                                                        |
|                   | +--------------------------------+ +----------------+ |
|                   | | Sales outlook                  | | Know the       | |
|                   | | solid actual / dashed forecast | | boundary       | |
|                   | | Explicit empty state           | | Model Studio > | |
|                   | +--------------------------------+ +----------------+ |
| Historical        | [ Dataset as-of? disclosure ] [ Actual vs prediction ] |
| workspace         | Historical workspace / source units disclaimer        |
+-------------------+--------------------------------------------------------+
```

The 240px sidebar gives stable destinations rather than a dashboard of unrelated widgets. Content width is bounded at 1440px; metric cards become columns only when space permits. The outlook contains no sample line, axes, accuracy, growth percentage, confidence band or total. Its empty state describes the next phase honestly.

## Mobile wireframe

```text
+----------------------------------+
| RetailForecast AI                |
| Overview         Forecasts       |
| Model Studio     Experiments     |
| Feature Explorer Data & Settings |
+----------------------------------+
| Dataset as-of [API date]          |
| [Model state] [API state] Refresh |
+----------------------------------+
| Overview                         |
| Purpose / action                 |
| Historical source notice         |
| Imported rows                    |
| Latest actual                    |
| Serving version                  |
| Sales outlook / explicit empty   |
| Know the boundary                |
| Methodology disclosures          |
+----------------------------------+
```

At narrow widths the same navigation becomes a wrapping two-column grid (three columns on medium widths). There is no hidden hamburger focus trap or hover-only destination. Cards stack, metadata wraps and tables scroll within their own container. Layout tests cover a 390px viewport; other browser zoom/device combinations still merit operator review.

## Design tokens

Use an 8px layout scale: 8/16/24/32/40/48px gaps, padding and section spacing. Small 4px internal label/icon offsets are optical adjustments; 44px controls are a deliberate touch-target exception. Surfaces use a 12px radius; controls 6–8px. System fonts avoid remote font downloads: Segoe UI, Arial, Helvetica, sans-serif. Body is 14–16px with generous line height; the page title is 30px. Tabular numerals keep counts/dates/amounts stable.

| Token | Value | Purpose |
|---|---|---|
| Background | #f7f8fa | Quiet workspace canvas |
| Card | #ffffff | Data/task surfaces |
| Foreground | #182536 | Main text |
| Muted text | #546174 | Secondary context, still readable |
| Primary | #244dcc | Actions, active navigation, observed series |
| Teal | #087983 | Predicted series and measured readiness cues |
| Border | #d7dee7 | Surface separation; not the only control boundary |
| Input boundary | slate-500 / #64748b | Stronger editable-control outline |

Measured contrast against white is 15.48:1 for main text, 6.29:1 for muted text, 6.98:1 for primary blue, 5.16:1 for teal and 4.76:1 for input boundaries. Recalculate if these tokens change. Selected navigation also uses weight/text and aria-current; readiness badges contain explicit words. Optional dark mode is deferred so the tested high-contrast light theme stays consistent.

No stock photos, generated artwork, decorative animations, template sales claims or invented operational results are used. Static skeletons preserve layout without unnecessary pulsing. Reduced-motion preference disables any inherited animation/transition.

## Shared component contracts and state coverage

All reusable foundation components live in apps/web/src/components/foundation/. shadcn/ui's local-owned composition pattern provides Button, Card, Badge, Input and Skeleton under components/ui; these retain native semantics, explicit labels and project tokens. Foundation tests cover each public component's relevant empty/loading/error state; route tests cover the shell and native keyboard behavior.

| Component | Input and behavior | Unavailable/state behavior |
|---|---|---|
| PageHeader | Title, purpose, optional actions; one h1 per normal page | No fake action when absent |
| MetricCard | Label, already formatted real value, context | Loading skeleton; empty/error label; never a synthetic zero/trend |
| EmptyState | Reason, explanation, optional working action | No fabricated illustration or result |
| DataFreshnessNotice | Observed date and loading/ready/error state | Missing source or unavailable freshness explicitly stated |
| StorePicker | Controlled store ID; bounded paged API search | Aborts stale reads; empty/error/retry; unsupported cohorts visibly disabled |
| DateRangePicker | Controlled date-only start/end, optional min/max | Empty instruction; reversed/invalid/out-of-range error; never silently swaps dates |
| ErrorBanner | Safe message, optional retry | Announced alert and real retry button |
| JobStatus | Typed persisted job or explicit unavailable state | Empty/loading/error and all six real job states; success does not imply activation |
| ChartShell | Bounded unique dates, explicit actual/predicted values | Empty/loading/error; no invented points; lazy renderer only for actual values |
| MethodologyHint | Short question and plain-language explanation | Native details/summary works with keyboard and touch |

Store/date pickers are reusable foundations tested in isolation. They are not presented as a working forecast form on a planned page. Store search pages are capped at 25 rows and retain forecast_supported from the API; imported stores outside the active model's cohort are never silently treated as supported. Query changes abort old requests and hide their old options immediately.

## Typed API plumbing

One timeout-bounded, same-origin apiRequest validates unknown JSON with Zod and rejects malformed, non-JSON and non-success responses. No credentials or private infrastructure URLs enter the browser. The Next.js server proxy retains API_BASE_URL. Existing health and training clients reuse this transport. The catalog contract validates date-only values, nonnegative counts, dataset IDs and store pages. Requests carry abort signals and no-store; errors never substitute sample data.

WorkspaceProvider issues three independent GETs: /api/v1/health, /datasets/status, /models/active. Overview derives all displayed values from those responses. Latest-import metadata and the active model's pinned source may differ; the notice and methodology explain that forecast compatibility is checked separately. Shared state is read-only; rendering/navigation/refresh never calls fit, POST /forecasts or POST /training-jobs. Model Studio preserves Phase 11's explicit user-click enqueue action and reads durable progress separately.

Business dates remain YYYY-MM-DD strings and display consistently as DD Mon YYYY with UTC formatting. An import timestamp is never formatted as an observed-sales date. Counts use English grouping. formatSales defaults to two displayed decimals plus “Sales units”; API/persisted values still retain their original precision. Currency formatting requires an explicit confirmed currency code and is not enabled for Rossmann by assumption. Missing values remain “Not available”; real zero remains 0.00.

## Apache ECharts boundary

The reusable renderer imports only ECharts core, line chart, grid, tooltip, ARIA and SVG renderer. It initializes after mount, resizes via ResizeObserver and disposes both observer and chart on unmount. It is lazy-loaded only when supplied validated nonempty values; an empty overview does not download/render mock chart data. Max 1,536 unique dated points bounds presentation memory. This component renders a prepared one-series-per-date view; upstream workflows must explicitly choose stores/aggregation and preserve cutoff provenance rather than silently aggregating here.

Historical actuals use a solid blue line; predicted sales use a dashed teal line. Legend text and separate series names repeat that distinction. connectNulls=false preserves missing-date gaps and never draws a continuous actual-to-prediction bridge. Animations are disabled. A keyboard-readable data table exposes every supplied date/value and preserves null versus zero even if the renderer fails. No unsupported confidence interval or performance score is inferred. The foundation has no production sales-history endpoint/view yet, so representative screenshots show the genuine empty chart; unit lifecycle tests use clearly synthetic fixtures only.

Reference implementation sources: [shadcn/ui theming](https://ui.shadcn.com/docs/theming), [Skeleton](https://ui.shadcn.com/docs/components/base/skeleton), [ECharts modular imports](https://echarts.apache.org/handbook/en/basics/import/), [ECharts sizing/disposal](https://echarts.apache.org/handbook/en/concepts/chart-size/). These describe library patterns; project contracts and tests remain the implemented source of truth.

## Accessibility checklist

- A visible-on-focus “Skip to content” link moves focus to the single main landmark.
- Real links navigate; real buttons act. Six labeled destinations have an explicit active-page marker.
- Each input has a programmatic visible label; errors attach through aria-describedby/aria-invalid. Native date controls preserve platform keyboard support.
- Focus indicators are high-contrast with offset. Controls are at least 44px tall. Native disclosures avoid hover-only help.
- Status updates announce briefly and independently; job failures are alerts without hiding an incumbent. No fake progress percentages.
- Chart meaning uses text and line pattern as well as color; the data table is the keyboard alternative.
- Sidebar/nav/content remain available offline. Loading, empty and failure states have distinct language.
- Browser checks use axe WCAG 2 A/AA and 2.1 A/AA tags on real desktop/mobile pages plus explicit keyboard/overflow tests. Automated checks are not a claim of full accessibility conformance; screen-reader/OS date-control and broad zoom testing remain manual review items.

## Reproduce and inspect

Run the normal API/web commands from README after PostgreSQL and migrations. Build/lint/types/component checks use npm run build, npm run lint, npm run typecheck, npm run test --workspace apps/web. Browser tests use npm run test:e2e. If normal ports are occupied, use the isolated API/web-port guidance in TRAINING_JOBS.md and build with the matching API_BASE_URL first; restore the normal proxy after verification.

Representative desktop/mobile images are saved only from a running real API state, after validation and visual inspection. Test-only no-model/offline transports remain fixtures, never public screenshots of alleged operational results. PHASE_12_REPORT.md records the actual commands, results, screenshot locations and scope limits.


## Verified running screenshots

Captured from the current production build and real local API after status settled, then visually reviewed. The data date, labeled-row count and active-version prefix are genuine metadata. The empty outlook is intentional, not a fabricated forecast.

[Desktop overview](screenshots/phase12/overview-desktop.png) · [Mobile overview](screenshots/phase12/overview-mobile.png)
