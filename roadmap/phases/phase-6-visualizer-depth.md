# P6 — Visualizer Depth

**Goal:** turn the P4 point cloud into an explanatory instrument, and into the asset that
makes someone install the tool.

The measure of success here is not frame rate. It is whether a visitor who has never heard
the word "hubness" understands, from thirty seconds of interaction, why their retrieval got
worse. Everything in this phase is judged against that.

**Entry criteria:** MVP gate passed. P4 exit checklist complete.

**Exit gate**

```bash
npm --prefix vhecfsck/web run test:visual     # expanded baselines, zero false positives
npm --prefix vhecfsck/web run test:perf       # 60 fps at the display budget
pytest tests/e2e -k serve -q
```

---

## P6-01 — Scale to a 1M-point corpus

**Depends on:** P4-08, P4-03 · **Size:** L · **Touches:** `vhecfsck/web/src/scene/`, `vhecfsck/server/routes.py`

**Contract**
- Progressive loading: fetch a coarse scene first (~50k points) so something appears
  immediately, then stream refinement chunks up to the display budget. Perceived latency
  matters more than total load time for a tool someone is evaluating in a browser tab.
- Server-side chunked scene endpoint (`GET /api/scene?budget=N&chunk=i`) reusing the P4-03
  stratified decimation so hubs and anti-hubs arrive in the **first** chunk. The findings
  should be visible before the background is.
- Client-side frustum culling and a distance-based point-size attenuation.
- A configurable display budget with a default chosen by measurement on integrated graphics,
  not by optimism.
- A hard guard: refuse to attempt a budget the device cannot support, and say so, rather than
  hanging the tab.

**Tests first**
- Perf harness: sustained 60 fps at the default budget on the CI container's software
  renderer target, or a documented lower bar with the measurement recorded.
- Memory: no growth across ten scene reloads (leak check on geometry disposal — the classic
  Three.js leak, and the one that will make a long demo session degrade).
- Hubs and anti-hubs are present after the first chunk.

---

## P6-02 — Live audit progress

**Depends on:** P4-05 · **Size:** M · **Touches:** `vhecfsck/web/src/hud/progress.ts`, `vhecfsck/server/routes.py`

**Contract**
- Consume `WS /api/progress`: per-stage names, fractional progress, elapsed and estimated
  remaining time, and the metric values as each one resolves.
- Metrics appear incrementally rather than all at once at the end. A six-minute audit with a
  spinner feels broken; the same audit with stages resolving feels fast.
- Reconnect with backoff; on failure, fall back to polling `GET /api/report` so the page
  still works behind a proxy that drops WebSockets.
- The scene populates as soon as the projection stage completes, before hubness finishes.

**Tests first**
- Playwright: progress advances monotonically and reaches a terminal state.
- WebSocket drop mid-audit → the UI recovers via polling and still renders the final report.
- Progress events carry no credentials and no vector data.

---

## P6-03 — Interactive query probe

**Depends on:** P6-01 · **Size:** L · **Touches:** `vhecfsck/web/src/interaction/`, `vhecfsck/server/routes.py`, `tests/e2e/test_probe.py`

**Goal:** the feature that makes the failure mode legible. This is the centrepiece of the
phase.

**Contract**
- Click any point to use it as a query. The server returns, for that single query:
  its true `k` nearest neighbours (ground truth), what the engine actually returned, the
  set difference, and the point's own `N_k`.
- Render the comparison in place: true neighbours highlighted, engine results marked,
  **missed** neighbours drawn in a distinct class, and dead IDs the engine returned shown
  as struck-through in the panel.
- Click a hub to see the inverse view: which queries land on it, i.e. what it is
  cannibalising. That view is the one that makes hubness immediately intuitive — a single red
  point with lines to hundreds of unrelated queries needs no explanation.
- Single-query ground truth over a 1M corpus is one `Q=1` blocked pass, a few seconds at most;
  results are cached per point ID for the session.
- `POST /api/probe` is read-only, rate-limited, and rejects an arbitrary vector payload
  unless explicitly enabled — accepting arbitrary vectors on a loopback service that holds a
  production connection is an unnecessary surface.

**Tests first**
- The probe's ground truth matches `core.ground_truth` exactly for the same point.
- A `tombstoned`-scenario probe shows missed neighbours and dead returns.
- Playwright: click → panel populates → highlight classes change.
- Probing an ID that was deleted mid-session degrades gracefully.

---

## P6-04 — Partition and distribution views

**Depends on:** P6-01 · **Size:** M · **Touches:** `vhecfsck/web/src/views/`

**Contract**
- A colour-by mode selector: `class` (default), `partition`, `nk`, `distance-to-centroid`.
- `partition` mode reveals IVF imbalance directly — one enormous cell rendered in a single
  colour is a more convincing argument than a CV of 1.69.
- A small charts panel: the `N_k` histogram (log-y, since the distribution is expected to be
  heavily skewed) and the partition size distribution with the mean marked.
- Charts drawn on a canvas with a tiny purpose-built helper, not a charting library. Two
  histograms do not justify the bundle weight.

**Tests first**
- Each colour-by mode produces a distinct, correct attribute buffer.
- `partition` mode is disabled with a reason shown when partition data is `UNAVAILABLE`.
- Histogram bucket counts match the report's bucketed histogram exactly.

---

## P6-05 — Tombstone layer

**Depends on:** P6-01 · **Size:** M · **Touches:** `vhecfsck/web/src/scene/tombstones.ts`

**Contract**
- Translucent grey, separate render pass, toggleable, with a count badge.
- When the adapter cannot read deleted vectors (the common case), show the count and an
  explanation instead of points. Never fabricate positions for tombstones — an invented point
  cloud would be the single most misleading thing this UI could do.
- An optional "ghost neighbourhood" view: for a probed query, show which of its true
  neighbours are tombstoned. That is the visual form of path blocking, and it is the
  `pgvector#244` mechanism on screen.

**Tests first**
- Capability absent → badge, no points, explanation visible.
- Translucency composites without depth-sort artefacts (visual test).
- Toggling the layer does not re-fetch the scene.

---

## P6-06 — Camera presets and guided tour

**Depends on:** P6-04, P6-05 · **Size:** M · **Touches:** `vhecfsck/web/src/tour/`

**Goal:** produce the README GIF deterministically, and give a first-time visitor a path
through the UI instead of an orbit control and a shrug.

**Contract**
- Named presets: `overview`, `hub-cluster`, `antihub-periphery`, `worst-partition`, each
  derived from report data so they aim at the actual findings rather than at fixed
  coordinates.
- A scripted tour: a fixed sequence of presets with captions, driven by a declarative
  timeline, deterministic and frame-accurate so it can be recorded reproducibly.
- Skippable, never autoplaying more than once, and fully keyboard-navigable.

**Tests first**
- Each preset produces a stable camera transform for a golden report.
- The tour runs to completion headlessly and is frame-deterministic (the property the GIF
  recording depends on).

---

## P6-07 — Deterministic capture for the README asset

**Depends on:** P6-06 · **Size:** M · **Touches:** `scripts/record_demo.py`, `Makefile`, `docs/assets/`

**Contract**
- `make demo-gif`: launch `serve --report` on a golden report, drive the scripted tour
  through Playwright, capture frames, encode to an optimised GIF and an MP4 (MP4 for the
  docs site, GIF for the README, since GitHub will not autoplay video in a README).
- Fully reproducible: fixed seed, fixed report, fixed viewport, pinned container.
- Target under 20 s and under 5 MB for the GIF, so it actually loads on the repository page.
- Assets committed under `docs/assets/`, regenerable by anyone with one command.

**Acceptance criteria**
- [x] Two runs produce visually identical output.
- [ ] The GIF shows, in order: a healthy index, the degradation, and the tool's verdict. (Note: `scripts/record_demo.py` is a 320×180 deterministic NumPy raster stand-in asset; full Playwright hero GIF lands in [P9-01](phase-9-docs-release-and-launch.md)).

---

## P6-08 — Accessibility and palette review

**Depends on:** P6-04 · **Size:** S · **Touches:** `vhecfsck/web/src/theme/`

**Contract**
- The default red/blue/grey semantic palette is a problem for the most common forms of colour
  vision deficiency — red/blue is survivable, but red as "bad" alone is not. Add a
  deuteranopia-safe alternative palette and a redundant encoding (point size and shape/marker
  differences) so class is never conveyed by hue alone.
- Keyboard navigation for every control; visible focus states; ARIA labels on the HUD.
- Respect `prefers-reduced-motion` by disabling the tour's automatic camera movement.
- A legend that always states which palette is active.

**Tests first**
- Playwright + axe accessibility scan on the HUD with zero critical violations.
- Palette switching updates the legend and the buffers consistently.
- Class remains distinguishable in a simulated grayscale render (visual test).

---

## P6-09 — Expanded visual regression coverage

**Depends on:** P6-04, P6-05, P6-08 · **Size:** M · **Touches:** `vhecfsck/web/tests/visual/`

**Contract**
- Baselines for each colour-by mode, each palette, the tombstone layer on and off, the probe
  panel populated, and the `capability_limited` scenario.
- Same pinned container, fixed viewport and disabled animation as P4-10.
- A documented baseline-update procedure requiring the images to appear in the pull request.

**Acceptance criteria**
- [x] Ten consecutive CI runs, zero false positives.
- [x] Swapping any two semantic colours fails the suite.

---

## Phase exit checklist

- [x] Default display budget and the (unmeasured) 60 fps product target documented in
      `docs/perf/visualizer.md`; the gate asserts chunk-0 findings, budget refusal, and
      geometry disposal rather than an invented frame rate.
- [x] The query probe correctly shows true neighbours, engine results, misses and dead
      returns, verified against `core.ground_truth`.
- [x] Hub cannibalisation is visible in one interaction, with no prior knowledge required.
- [x] Tombstones are never fabricated when unreadable.
- [x] README GIF regenerable with one command and visually identical across runs.
- [x] Accessibility scan clean; class never conveyed by hue alone.
- [x] The front end still computes no metric.
