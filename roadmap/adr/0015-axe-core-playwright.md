# ADR-0015 — @axe-core/playwright for Visualizer Accessibility E2E Testing

**Status:** Accepted
**Affects:** P4, P6, P9

## Context

ADR-0010 established Vite, TypeScript, Vitest, and Playwright for the visualizer front end. While Vitest runs fast in-process WCAG heuristic checks using internal DOM helpers, verifying true browser accessibility rendering (including focus management, ARIA tree computed states, color contrast, and control surface keyboard navigation) in real headless Chromium requires automated browser auditing tooling.

Guardrail 2 requires an ADR for any new front-end or Python dependency.

## Decision

- Add **`@axe-core/playwright`** as a devDependency in `vhecfsck/web/package.json`.
- `@axe-core/playwright` runs accessibility audits inside Playwright headless Chromium browser sessions, asserting zero critical WCAG violations on the visualizer HUD control surface.
- `@axe-core/playwright` is strictly a development and test dependency. It is never included in the production JS bundle shipped with `vhecfsck`.

## Consequences

**Buys:**
- Automated end-to-end WCAG accessibility regression testing in real browser rendering engines.
- Complements Vitest in-process DOM checks with full computed accessibility tree verification.

**Costs:**
- Minor addition to devDependencies in `vhecfsck/web/package.json` and lockfile.
