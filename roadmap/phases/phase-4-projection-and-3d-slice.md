# P4 — Projection and 3D Slice (showcase branch)

**Goal:** close the vertical slice. Make an invisible failure mode visible.

The output of this phase is deliberately unimpressive in feature count and complete in shape:
a real report, projected into 3D, rendered in a browser, with hubs red, anti-hubs blue and
tombstones translucent grey. Depth arrives in [P6](phase-6-visualizer-depth.md). What matters
here is that the report schema proves sufficient to drive a visualizer *before* anyone builds
an elaborate one against assumptions.

**Entry criteria:** P3 exit checklist complete.

**Exit gate**

```bash
pytest tests/e2e -q
npm --prefix vhecfsck/web test
vhecfsck demo --serve --no-browser &   # then GET /api/report and /api/scene return 200
```

---

## P4-01 — Deterministic 3D projection

**Depends on:** P2-04 · **Size:** M · **Touches:** `vhecfsck/core/projection.py`, `tests/unit/test_projection.py`, `tests/property/test_projection_props.py`

**Contract**
- `project_to_3d(vectors_iter, *, n_components=3, seed, sample_size) -> Projection`
  using incremental PCA over streamed blocks, so 1M × 768 never needs to be held twice.
- **Deterministic component signs.** PCA components are sign-ambiguous: the same data can
  legitimately yield `+v` or `-v`, which would mirror the scene between runs and make visual
  regression testing impossible. Fix the sign by forcing the element of largest absolute
  value in each component to be positive (the `svd_flip` convention), and test it.
- Output normalised into a fixed display cube (`[-1, 1]³`) with the scale factor recorded, so
  camera framing is stable across datasets.
- Reports `explained_variance_ratio` per component and their sum. A 768-dimensional embedding
  typically retains only 10–25% of variance in three components; that number must be shown
  in the UI, because a 3D projection of high-dimensional data is a *sketch*, and presenting
  it as ground truth would be dishonest.
- Projects live vectors and, when the adapter can read them, tombstoned vectors too, in the
  same fitted basis so the two layers are comparable.

**Tests first**
- Same seed and input → bit-identical output; sign convention holds when input is negated.
- Rotation of the input rotates the projection but preserves pairwise distance ordering
  within a documented tolerance.
- Incremental result matches a single-shot PCA on a small input within `1e-4`.
- Degenerate inputs: rank-1 data, fewer than 3 vectors, all-identical vectors — each handled
  explicitly rather than raising from inside NumPy.
- `explained_variance_ratio` sums to ≤1 and is monotonically decreasing.

**Acceptance criteria**
- [ ] 1M × 768 projected within the memory budget, in under 60 s.
- [ ] No `float64` copy of the corpus is ever materialised.

---

## P4-02 — Scene payload model

**Depends on:** P3-01, P4-01 · **Size:** M · **Touches:** `vhecfsck/models/scene.py`, `tests/unit/test_scene_model.py`

**Contract**
- `PointClass` enum: `HEALTHY`, `HUB`, `ANTIHUB`, `TOMBSTONE`, `QUERY`, `TRUE_NEIGHBOUR`,
  `RETURNED`, `MISSED`. The last four exist for the P6 query probe and are defined now so the
  schema does not need to change then.
- `ScenePayload`: positions (`float32`, `(n, 3)`), `classes` (`uint8`), optional `partition_id`
  (`int32`), optional `nk` (`int32`), `ids` (`int64`), plus `lod` metadata (requested budget,
  actual count, decimation method, whether the scene is complete or sampled).
- **Point IDs are opaque integers.** No payload text, no metadata columns, no source
  documents ever enter a scene — the scene is served over HTTP and may be screenshotted into
  a public issue.
- Colour semantics are declared in the model as a constant mapping and consumed by the front
  end, so the legend cannot drift from the renderer.

**Tests first**
- Array lengths agree across every field; dtypes enforced.
- A tombstone layer is present only when the adapter can read deleted vectors, and the
  payload states which case applies rather than leaving the front end to infer it from an
  empty array.

---

## P4-03 — Level-of-detail decimation

**Depends on:** P4-02 · **Size:** M · **Touches:** `vhecfsck/core/projection.py` (or `core/lod.py`), `tests/unit/test_lod.py`

**Goal:** implement [ADR-0009](../adr/0009-scene-transport-and-lod.md). A million points sent
as JSON is roughly 300 MB and will not render; naive random sampling to 200k would drop
exactly the rare points the tool exists to show.

**Contract**
- `decimate(scene, budget, *, seed) -> ScenePayload` with **class-stratified** sampling:
  every `HUB`, `ANTIHUB` and `QUERY` point is retained up to its own cap, and `HEALTHY`
  points absorb the remaining budget. Losing a hub to random sampling would silently remove
  the finding.
- Spatially aware thinning within the healthy class (grid-bucket one point per occupied
  voxel before random fill), so the visual shape of the corpus survives decimation.
- Deterministic under a fixed seed; records the method and the retention ratio per class in
  `lod` metadata, and the UI displays "showing 200k of 1.04M points".

**Tests first**
- Every hub and anti-hub survives decimation while the budget allows.
- Output size ≤ budget; deterministic under seed.
- Class proportions after decimation match the declared retention policy.
- A scene already under budget passes through unchanged, with `complete = true`.

---

## P4-04 — Binary scene transport

**Depends on:** P4-02 · **Size:** M · **Touches:** `vhecfsck/server/schemas.py`, `vhecfsck/report/scene_codec.py`, `tests/unit/test_scene_codec.py`

**Contract**
- Encode a `ScenePayload` as a small JSON header (counts, dtypes, offsets, `lod`, legend)
  plus concatenated raw little-endian typed-array buffers, served as
  `application/octet-stream`. The front end wraps the buffers in typed arrays with zero
  parsing and zero copying.
- Explicit endianness handling with a documented assumption of little-endian and an
  assertion on the (currently hypothetical) big-endian host, rather than a silent
  byte-order bug.
- Optional `gzip`/`zstd` via standard content negotiation; never a custom compression scheme.
- A `--format json-scene` debug path exists for human inspection of small scenes, clearly
  marked as unsuitable for large ones.

**Tests first**
- Round-trip: encode → decode → arrays bit-identical.
- Buffer offsets are correctly aligned for `Float32Array` construction — misalignment throws
  in the browser, and it throws in a way that is genuinely hard to debug from a stack trace.
- A 1M-point scene encodes in under 1 s and produces a payload under 20 MB before
  compression.
- A parallel decoder in the TypeScript test suite validates the same fixture, so the two
  sides of the wire are tested against one artifact rather than against each other's
  assumptions.

---

## P4-05 — FastAPI server

**Depends on:** P4-04, P2-10 · **Size:** M · **Touches:** `vhecfsck/server/app.py`, `vhecfsck/server/routes.py`, `tests/e2e/test_server.py`

**Contract**
- Endpoints:
  - `GET /api/health` → liveness.
  - `GET /api/report` → the report JSON.
  - `GET /api/scene?budget=N` → binary scene payload.
  - `GET /metrics` → the P3-06 Prometheus rendering.
  - `POST /api/audit` → run an audit with the current config (single-flight; a second
    concurrent request gets `409`, because two 1M-vector audits at once will exhaust memory).
  - `WS /api/progress` → progress events during an audit.
  - `GET /` → the static SPA.
- **Bound to `127.0.0.1` by default.** No authentication, no CORS. Binding to `0.0.0.0`
  requires an explicit `--host` and prints a warning, because this process holds a read
  connection to a production database and has no auth layer.
- Read-only: no endpoint mutates the target. `POST /api/audit` re-reads, nothing more.
- Reuses `report/` renderers; contains no metric logic (import-linter enforced).

**Tests first**
- Every endpoint's status code and content type, via `httpx`.
- Concurrent `POST /api/audit` → `409`.
- Default bind address is loopback; `--host 0.0.0.0` emits the warning.
- WebSocket receives ordered progress events and a terminal event.
- No credential appears in any response, including error responses.

---

## P4-06 — `vhecfsck serve`

**Depends on:** P4-05 · **Size:** S · **Touches:** `vhecfsck/cli.py`, `tests/e2e/test_cli_serve.py`

**Contract**
- `vhecfsck serve --target <uri> [--port 8765] [--host 127.0.0.1] [--no-browser] [--report PATH]`.
- `--report` serves a stored report with no target connection at all — the shareable mode,
  and the one used to produce the README GIF.
- Opens a browser by default; `--no-browser` for tests and headless use.
- `serve` requires the `[server]` extra and says so clearly if it is missing.
- Ctrl-C shuts down cleanly, closing the adapter.
- The contributor `setup.sh` Heart of Gold action runs this command in the **foreground**.
  Do not turn `setup.sh` into a process supervisor when this lands.

**Tests first**
- Starts, serves, and shuts down in a subprocess without leaking a port.
- `--report` mode never opens an adapter (asserted with a fault-injecting stub target).
- Missing extra → exit `4` with the install hint.

---

## P4-07 — Front-end scaffold

**Depends on:** P0-10 · **Size:** M · **Touches:** `vhecfsck/web/package.json`, `vite.config.ts`, `tsconfig.json`, `vhecfsck/web/src/`, `vhecfsck/web/tests/`

**Contract**
- Vite + TypeScript in `strict` mode, Vitest for units, Playwright for browser tests
  ([ADR-0010](../adr/0010-frontend-build-and-bundling.md)).
- ESLint + Prettier, wired into `make verify` through a `web-lint` target.
- No framework. This is one canvas and a small HUD; React would be more build surface than
  code.
- Dev server proxies `/api` to the FastAPI backend.
- `npm test` runs unit tests headlessly and is added to CI.

**Acceptance criteria**
- [ ] `npm ci && npm run build && npm test` green from a clean clone.
- [ ] Production bundle under 500 KB gzipped, with Three.js tree-shaken.
- [ ] Node is required for development only, never for installing the wheel.

---

## P4-08 — Point-cloud renderer

**Depends on:** P4-07, P4-04 · **Size:** L · **Touches:** `vhecfsck/web/src/scene/`, `vhecfsck/web/tests/unit/`

**Contract**
- Fetch the binary scene, wrap buffers in typed arrays, upload once as a
  `THREE.BufferGeometry`, render with a single `THREE.Points` draw call and a custom shader
  material.
- Per-point colour from the `classes` array via a texture or vertex attribute lookup, using
  the legend from the payload — the front end never hardcodes a colour mapping.
- Tombstones render with reduced opacity and are drawn in a separate pass with depth-write
  disabled, so translucency composites correctly instead of producing sort artefacts.
- `OrbitControls`, a reset-view button, and a fixed default camera framing derived from the
  normalised display cube.
- Zero per-frame allocation; zero per-point JavaScript objects. Anything else will not hold
  60 fps at 200k points.
- Graceful degradation: no WebGL2 → a clear message plus a link to the JSON report, not a
  blank canvas.

**Tests first**
- Unit: buffer decoding matches the fixture produced by the Python codec (shared artifact).
- Unit: class-to-colour mapping matches the legend.
- Unit: geometry attribute counts equal the payload counts.
- Playwright: the canvas is non-blank and the reported draw-call count is 2 (opaque plus
  translucent pass).

---

## P4-09 — Report HUD

**Depends on:** P4-08 · **Size:** M · **Touches:** `vhecfsck/web/src/hud/`, `vhecfsck/web/tests/unit/`

**Contract**
- A panel showing the verdict, each metric with its value, threshold and state, the target
  descriptor, and the sampling parameters actually used.
- The projection's `explained_variance_ratio` is displayed prominently with a one-line caveat
  that 3D is a lossy sketch of 768 dimensions. Not a footnote — a visitor who mistakes the
  projection for the truth will draw wrong conclusions and blame the tool.
- The LOD banner: "showing 200,000 of 1,043,133 points (class-stratified)".
- A legend generated from the payload's colour mapping.
- `UNAVAILABLE` metrics shown with their reason, visually distinct from `OK`.
- Keyboard shortcuts for layer toggles (hubs, anti-hubs, tombstones, healthy).

**Tests first**
- Unit: renders every metric state, including `UNAVAILABLE` and `DISABLED`, from golden
  report fixtures — the same golden files the Python tests use.
- Unit: layer toggles change visibility flags without re-fetching the scene.
- Playwright: HUD text contains the verdict for the `tombstoned` scenario.

---

## P4-10 — Visual regression baseline

**Depends on:** P4-09 · **Size:** M · **Touches:** `vhecfsck/web/tests/visual/`, `.github/workflows/ci.yml`

**Contract**
- Playwright screenshot comparison against a committed baseline for two canonical scenes
  (`healthy`, `tombstoned`), driven by `serve --report` on a golden report so the images
  depend on nothing but the renderer.
- Fixed viewport, fixed camera, fixed seed, animation disabled, and `--force-device-scale-factor=1`.
- Runs in a pinned Playwright container so GPU/driver differences do not produce false
  diffs — the standard failure mode of visual testing, and the reason most teams abandon it.
- A pixel-difference tolerance chosen by measuring actual run-to-run variance, not guessed.

**Acceptance criteria**
- [ ] Ten consecutive CI runs produce zero false positives.
- [ ] Baselines are updated only through an explicit command, with images visible in the pull
      request diff.
- [ ] Deliberately swapping the hub and anti-hub colours fails the test.

---

## P4-11 — Bundle the front end into the wheel

**Depends on:** P4-07, P0-01 · **Size:** M · **Touches:** `pyproject.toml`, `hatch_build.py`, `.github/workflows/release.yml`

**Contract**
- A Hatch build hook runs `npm ci && npm run build` and includes `vhecfsck/web/dist` in both
  the wheel and the sdist (`hatch_build.py`).
- `dist/` is **not** committed to the repository; it is a build artifact. The sdist ships the
  prebuilt output so that installing from source needs no Node.
- If `dist/` is absent at runtime, `serve` fails with an actionable message ("built from a
  git checkout: run `make web-build`") instead of a `404` on `/`.
- CI verifies that a wheel installed into a clean, Node-free environment can serve the SPA —
  the exact property that breaks silently and is only noticed by a user. (Note: HYG-02 landed `hatch_build.py` and unit/slow packaging tests; Node-free clean machine CI wheel smoke residual belongs to P9-05).

**Acceptance criteria**
- [x] Custom `hatch_build.py` hook compiles front-end assets and includes `vhecfsck/web/dist/index.html` in wheel and sdist.
- [ ] `pip install dist/*.whl` into a Node-free venv in CI release workflow (residual for [P9-05](../phases/phase-9-docs-release-and-launch.md)).
- [ ] Wheel size under 10 MB (measured local wheel ~500 KB gzipped / ~2 MB uncompressed).

---

## Phase exit checklist — this is the MVP gate

Run the full MVP checklist in [`03-phases-overview.md §4`](../03-phases-overview.md). In
addition:

- [ ] The 3D view is driven entirely by report and scene data; the front end computes no
      metric (verified by review of `web/src`).
- [ ] Hubs are red, anti-hubs blue, tombstones translucent grey, asserted by visual
      regression.
- [ ] The projection's explained-variance caveat is visible in the UI.
- [ ] `uvx vhecfsck demo --serve` works end to end on a clean machine.
- [ ] The report schema required **no** change to accommodate the visualizer. If it did, that
      is the finding this phase existed to produce — record it in
      [ADR-0008](../adr/0008-report-schema-versioning.md).
