# 0004 — Runnable skeleton boundaries and tooling

## In plain English
The starter proves that the browser can reach the local API. It does not import data or make predictions. One Python package keeps future business code together. The two development services can run without a database or cloud account. Tooling is locked and checks real connection behavior.

Date: 2026-10-19. Status: Implemented scaffold, verification recorded in implementation log.

## Decisions and trade-offs
Use src/retailforecast as the only installable Python package root. services/api/main.py is a thin top-level service entry point; no second domain package is introduced. Domain submodules are documented empty boundaries. Use a same-origin Next.js rewrite for browser API calls; no CORS/auth stack is needed for loopback liveness. Health reports process liveness only, not future dependency readiness.

Use uv/uv.lock with exact direct Python versions, npm workspaces/package-lock.json with exact direct frontend versions, Ruff, strict mypy/TypeScript, ESLint TypeScript/React Hooks rules, Prettier, pytest, Vitest, and Playwright. Current test/lint tooling needs Node 22.13+. The old system Node remains unchanged; a checksum-verified ignored portable Node 22 supports local checks. Python 3.11 is the tested baseline.

Use standard ESLint rules instead of eslint-config-next: the initial preset introduced an unfixed braces dependency chain flagged by npm audit. No audit suppression or forced framework downgrade was used. Keep shadcn/ui configuration and a locally owned Radix/CVA button. Avoid remote fonts and charts/ML dependencies until their implementation phase.

The Python launcher supervises two logical services and stops descendants on exit. Framework/supervisor child processes mean this is not a promise of exactly two OS PIDs. Infrastructure and the future training scheduler remain separate and unimplemented. Raw dataset files are preserved; only empty raw/processed/artifact directory markers are eligible for Git.
