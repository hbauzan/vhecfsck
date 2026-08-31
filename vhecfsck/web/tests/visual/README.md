# Visual regression baselines (P6-09)

These tests live in `vhecfsck/web/tests/visual/` (in-process Vitest buffer baselines) and `vhecfsck/web/tests/e2e/` (real headless Chromium Playwright baselines).

## Running In-Process Vitest Baselines

```bash
npm --prefix vhecfsck/web run test:visual
```

They compare palette buffers, marker coverage, tombstone-layer policy, the populated
probe panel, and the `capability_limited` explanation. Animation is disabled by not
starting the tour.

## Running Playwright Real Browser Baselines

```bash
npm --prefix vhecfsck/web run test:e2e
# or
make web-test-e2e
```

Playwright verifies real WebGL2 non-blank rendering, draw calls, screenshot regressions (`healthy` and `tombstoned`), HUD verdict rendering, probe interaction, WebSocket resilience polling recovery, and WCAG accessibility via `@axe-core/playwright`.

## Updating a Baseline

1. Change the buffer, HUD assertion, or screenshot expectation in `baselines.test.ts` or `tests/e2e/`.
2. Run `npm --prefix vhecfsck/web run test:visual` and `npm --prefix vhecfsck/web run test:e2e` to confirm expected failure behaviour (swapping hub/anti-hub colours must fail).
3. Update snapshots if needed: `npx --prefix vhecfsck/web playwright test --update-snapshots`.
4. Commit the test change in the same pull request as the PNG images or buffer expectations it introduces. Do not land a baseline update without the image or hex dump visible in the diff.

## Demo GIF Canonical Generator

`make demo-gif` (`scripts/record_demo.py`) remains the canonical, deterministic README GIF generator producing a byte-identical output (<5 MB). The Playwright visual regression suite complements it by auditing real browser WebGL rendering without replacing `record_demo.py`.
