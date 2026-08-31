# Testing Strategy

The premise of this project is that it reports honest numbers about someone else's production
system. A wrong number is worse than a missing number, because a wrong number gets trusted and
acted upon. That single fact sets the quality bar and dictates the whole approach.

The central technique is available to us because of
[ADR-0003](adr/0003-empirical-metrics-only.md): since every metric is a count, a ratio, or a
direct measurement, **every metric has a naive implementation that is obviously correct**. That
gives every optimised implementation an independent oracle, which is a luxury most numerical
projects do not have — and the reason coverage is not the primary quality signal here.

---

## 1. Test layers

| Layer | Directory | Answers | Runs |
| :--- | :--- | :--- | :--- |
| Unit | `tests/unit/` | Does this function do what its contract says on inputs I can verify by hand? | Always |
| Property | `tests/property/` | Do the invariants hold on inputs I did not think of? | Always |
| Oracle | `tests/oracle/` | Does the fast implementation agree with the obviously-correct one? | Always |
| Contract | `tests/contract/` | Does this adapter satisfy the protocol, including its unavailable paths? | Always |
| E2E | `tests/e2e/` | Does the CLI, the server, and the report behave as documented? | Always |
| Integration | `tests/integration/` | Does it work against a real engine? | CI + on demand |
| Perf | `tests/perf/` | Is it still within budget? | Nightly |
| Visual | `vhecfsck/web/tests/visual/` | Does it still look right? | CI |
| Mutation | (tooling) | Would a wrong line actually be caught? | Nightly |

### 1.1 Unit — hand-verifiable fixtures

The highest-value unit tests in this project are the three hand-computed fixtures in
[`02-metrics-spec.md`](02-metrics-spec.md), each verified numerically before being written down:

- **Fixture A** (canary): 6 vectors in 2D where `recall_id == 0.5` and `recall_dist == 1.0`. The
  regression test for [ADR-0007](adr/0007-tie-tolerant-recall.md).
- **Fixture B** (hubness): 4 points in 1D where `N_k == [1, 2, 1, 0]`.
- **Fixture C** (partitions): sizes `[500, 500, 500, 80000]` where `cv ≈ 1.6895464932727084`.

These are small enough to check with a pencil, which is exactly why they are trustworthy. They
must never be deleted or "modernised".

### 1.2 Property — invariants over generated inputs

Hypothesis-driven. The invariants worth encoding are the ones that a plausible bug would break:

- **Bounds:** every ratio metric ∈ `[0, 1]`; `cv >= 0`.
- **Permutation invariance:** shuffling corpus row order must not change any metric. This catches
  a surprising range of indexing bugs.
- **Rotation invariance:** a global orthogonal rotation must not change hubness (distances are
  preserved).
- **Scale invariance:** for cosine, positive scaling of all vectors changes nothing; for partition
  CV, uniform scaling of all sizes changes nothing.
- **Monotonicity:** more deletions → higher DFI; more mass concentrated in one cell → higher CV;
  injected hubs → higher hub share; injected outliers → higher anti-hub fraction; higher `nprobe`
  → recall does not decrease.
- **Internal invariants:** `sum(N_k) == S · k_hub`, exactly.
- **Determinism:** same seed → identical output, in-process and cross-process.

### 1.3 Oracle — differential testing

The core discipline: write the naive version first (`P2-03`), keep it forever, never optimise it.

- `naive_knn` vs blocked BLAS `exact_knn`: identical ID sets on tie-free inputs, distances within
  `1e-5` relative tolerance, across all three metric spaces and randomised shapes.
- **Block-size invariance** is the single most valuable oracle test: identical results at block
  sizes 1, 7, 999 and `n`. Block-boundary errors in the top-`k` merge are the likeliest defect and
  are invisible in aggregate statistics.
- `naive_nk` vs the blocked hubness path.
- A `float64` cross-check on a small slice, confirming the `float32` path preserves neighbour
  ordering.

### 1.4 Contract — one suite, every adapter

`tests/contract/test_adapter_contract.py` is parametrised over every adapter and run unmodified
for each. It is the definition of "a working adapter", and adding an engine means registering a
fixture, not editing the suite.

The rule that matters most: **for every capability an adapter declares `False`, the suite verifies
the `UNAVAILABLE` path.** Unsupported capabilities are tested, never skipped. A skipped test is
indistinguishable from a passing one at a glance, and that is precisely where a silent regression
would hide.

### 1.5 Read-only verification — the project's central claim

A dedicated harness (`P5-07`, extended in `P8-10`) that snapshots a target, runs a full audit, and
asserts zero observable change:

- **File-backed engines:** every file's size, mtime and SHA-256 identical; no new files, including
  version or cache entries.
- **Qdrant:** collection state, segment count and version identical.
- **pgvector:** the session is server-side read-only, and `pg_stat` write counters are unchanged.
- **Independent check:** the audit also runs against a read-only mount and with minimum-privilege
  credentials. A write that the engine swallowed silently would pass a hash comparison but fail
  here.
- **Negative control:** a deliberately injected write, in a test-only branch, must make the
  harness fail. An unvalidated harness is indistinguishable from no harness.
- **Zero egress:** the socket layer is monkeypatched to assert connections are made only to the
  configured target. Applies to the web bundle too — a remote font is an egress.

### 1.6 Reproduction tests — evidence, not illustration

Each anchor issue becomes an automated test with three parts, and the ordering matters:

1. **Prove the pathology exists**, independently of our tooling: recall degrades, latency rises,
   result sets go short, while the engine's own health signals stay green.
2. **Prove we detect it:** the expected metrics cross their thresholds and the exit code is
   non-zero.
3. **Prove the counterfactual:** after the operator remedy (rebuild, `VACUUM`), the metrics
   recover.

Without step 1, the test only proves our metric moved — which could happen for entirely unrelated
reasons. Without step 3, it could be passing by accident.

### 1.7 Perf — asserted budgets, not recorded timings

`pytest-benchmark` with budget assertions on the reference machine, whose specification is
published so users can scale the expectation. Nightly regression detection opens an issue rather
than failing a branch, because benchmark noise on shared runners would otherwise make the build
untrustworthy — and an untrustworthy build gets ignored.

### 1.8 Mutation — does the suite actually test anything?

Coverage says a line executed. Mutation testing says a *wrong* line would have been caught, which
is the property that matters for a tool whose output drives decisions.

Run nightly over `core/` and `models/`. The mutants that must be killed:

- Threshold comparison operators (`<` vs `<=`, `>` vs `>=`) — a flipped boundary silently changes
  every verdict at the edge.
- `ddof=0` → `ddof=1` in partition CV.
- Tie-break direction in top-`k` selection.
- Off-by-one in `ceil(0.01 · S)` for the top-1% hub share.

Every survivor is investigated. Zero survivors permitted in `verdict.py` and in threshold
comparisons.

---

## 2. Determinism

An invariant, not a nice-to-have ([`00-vision-and-scope.md §7`](00-vision-and-scope.md)).

- All randomness from named sub-streams derived from one root seed. Global RNG use is a lint
  failure.
- All ties break by ascending vector ID, everywhere.
- Tests pin `PYTHONHASHSEED` and single-threaded BLAS, because multi-threaded reduction order is
  not deterministic and would eventually produce a flaky test that costs a day to diagnose.
- Reports are byte-identical across runs after normalising a **frozen allowlist** of genuinely
  volatile fields (timestamps, durations, host facts). The allowlist being frozen is the point: a
  new non-deterministic value cannot be waved through by quietly adding it.
- Float formatting is fixed at the serialisation boundary so platform last-digit differences
  cannot break byte-identity.

---

## 3. Gates

| Gate | Threshold | Enforced |
| :--- | :--- | :--- |
| Line coverage, `core/` | ≥90% | `make verify` |
| Line coverage, overall | ≥80% | `make verify` |
| Branch coverage, `verdict.py` | 100% | `make verify` |
| `mypy --strict` on `core`, `models`, `adapters` | zero errors | `make verify` |
| Ruff lint + format | clean | `make verify` |
| Import layering | contracts satisfied | `make verify` |
| Read-only static guard | zero violations | `make verify` |
| Mutation score, `core/` | measured floor, ratcheted up | nightly |
| Visual regression | zero unapproved diffs | CI |
| Perf budgets | within band | nightly |
| Contract suite | zero skips in CI | CI |

Coverage is a floor, not a goal. 100% coverage of a metric with no oracle test proves nothing;
90% coverage plus a differential oracle plus property invariants plus a killed mutation set is
real evidence.

---

## 4. Fixture strategy

- **Small by default.** The inner loop (`make test` / the file you are editing) must stay
  cheap enough that agents and humans keep running it. The merge gate is `make verify`
  once per ticket; `verify-full` is the version-tag suite. A gate nobody runs is not a gate.
- **Generated, not committed.** Corpora come from the seeded synthetic generator. Committing a
  100 MB `.npy` is a repository problem forever.
- **Session-cached.** Expensive corpora are built once per session and reused.
- **Large fixtures are opt-in**, marked `slow`, and run nightly.
- **Golden reports are committed** (they are small), with volatile fields normalised by a shared
  helper and updates requiring an explicit `--update-golden` run so the diff appears in review.
- **One shared artifact across language boundaries:** the scene codec fixture is produced by
  Python and consumed by both the Python and TypeScript test suites, so the two sides of the wire
  are tested against one truth rather than against each other's assumptions.

---

## 5. CI structure

**Hosted GitHub Actions are disabled permanently** (2026-08-30). Private-repo runner
minutes cost money; `ci.yml` and `nightly.yml` keep the old recipes as comments plus an
inert `workflow_dispatch` stub that never runs on push or schedule.

**The gate is local:** `make verify` on the Darwin laptop. That *is* the old
macOS × 3.12 / Accelerate job.

**Linux × Python 3.11 / 3.12 / 3.13** (advisory 3.14) and **nightly** (`make verify-full`,
SDK drift) have no remote witness until [P9-10](phases/phase-9-docs-release-and-launch.md)
— post-launch TBD: the same recipes in Docker, optionally a `setup.sh` verb. Skip P9-10
while anything else is open. Docker does not reproduce macOS BLAS.

**Additionally, when those suites exist:** integration against containerised Qdrant and
PostgreSQL (P7-01: `testcontainers`, pinned tags, health-gated startup; local skip is
actionable, `CI=true` fails a skip), the LanceDB file-based suite, and visual regression
in a pinned container — still local / on demand, not GitHub-hosted.

**On release tag (P9-05):** full verification, build, publish to TestPyPI, install from
TestPyPI into a clean container and run the demo, then publish to PyPI. That smoke step
stays a release-engineering concern, not a billed Actions matrix.

---

## 6. What we deliberately do not test

Stated so nobody adds them out of completeness reflex.

- **Third-party engine correctness.** We measure engines; we do not verify their internals.
- **Every threshold value.** Thresholds are configuration; the *comparison logic* is tested
  exhaustively, and the values are justified by calibration measurement instead.
- **Exact float equality across BLAS implementations.** Tolerances are measured and documented.
- **Every Python × engine version combination.** A tested range per engine, with nightly drift
  detection.
- **The visual appearance of the 3D scene beyond the canonical baselines.** Visual regression at
  wider scope produces false positives that erode trust in the whole suite.
