# 0014 - Read-only workspace context and accessible UI foundations

Date: 2026-10-20. Status: implemented in Phase 12.

## Decision

Use one persistent responsive shell with six named destinations. Share independent read-only API-health, latest-import and active-pointer resources. Overview shows only actual metadata. Keep Phase 11's explicit training action in Model Studio. Mark incomplete feature destinations as planned browser workflows; do not synthesize charts or operational metrics to fill space.

Local-owned shadcn/ui primitives provide native semantics and shared tokens. Native date/select/details controls keep keyboard behavior straightforward without new popup/focus dependencies. One Zod-validated same-origin timeout transport handles health/catalog/jobs, while abort-aware resources cancel obsolete search reads. Format business dates in UTC and preserve unspecified Sales units; confirmed currency is explicit opt-in.

Use a modular lazy Apache ECharts SVG boundary for validated bounded points. Separate solid-blue actual and dashed-teal predicted series, keep missing gaps and expose a data table. Empty pages do not import/render fabricated chart data. Use real API screenshots only after browser/a11y verification; component fixtures are test-only.

## Trade-offs

Native paged store selection prioritizes maintainable semantics over a custom combobox; date controls retain OS-specific calendar appearance. The light theme is tested first, with optional dark mode deferred. Readiness snapshots refresh explicitly rather than adding background polling across every page. The chart foundation is implemented/tested without adding a historical-series endpoint or complete forecasting workflow. API offline/empty-model states remain useful for a public reviewer but do not claim a hosted live service.

## Verification

UI_DESIGN.md defines hierarchy/wireframes/component contracts and measured contrast. PHASE_12_REPORT.md records component, strict TypeScript, build, browser/keyboard/mobile/axe checks, genuine screenshots and scope limits. Backend health/OpenAPI spot checks ensure the shared client leaves existing API contracts unchanged. No training, forecast generation or dataset publication occurs on page rendering/navigation.
