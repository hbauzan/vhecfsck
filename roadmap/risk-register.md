# Risk Register

Risks that could sink the project or materially damage it. Each has a trigger to watch for, a
mitigation with an owning ticket, and a plan for what to do if it happens anyway.

Severity is judged by consequence, not probability. `R1` is rated critical despite being unlikely
precisely because its consequence is terminal.

| ID | Risk | Severity | Likelihood |
| :--- | :--- | :--- | :--- |
| [R1](#r1) | The tool writes to or corrupts a production index | Critical | Very low |
| [R2](#r2) | Uncalibrated thresholds cause false alarms, tool gets disabled | High | High |
| [R3](#r3) | A metric is silently wrong and gets trusted | Critical | Medium |
| [R4](#r4) | Engine API drift breaks adapters | Medium | High |
| [R5](#r5) | Ground truth cost makes the tool impractical at real scale | Medium | Medium |
| [R6](#r6) | Reading a live, mutating index yields inconsistent results | Medium | High |
| [R7](#r7) | Scope creep prevents the MVP from ever shipping | High | High |
| [R8](#r8) | Credential or data leak through reports, logs, or scenes | High | Low |
| [R9](#r9) | Visualizer cannot handle target scale | Medium | Medium |
| [R10](#r10) | Anchor issues are fixed or misrepresented at launch | Medium | Medium |
| [R11](#r11) | Nobody cares; no adoption | Medium | Medium |
| [R12](#r12) | Flaky integration tests erode trust in CI | Medium | High |
| [R13](#r13) | Reference dataset licensing problems | Low | Low |
| [R14](#r14) | Maintainer burden from adapters exceeds capacity | Medium | Medium |

---

## R1 — The tool writes to or corrupts a production index {#r1}

**Consequence:** terminal. One incident and the project is permanently unusable, regardless of any
subsequent fix. No feature is worth this risk.

**Triggers to watch:** a new adapter added by a contributor unfamiliar with the invariant; an
engine SDK method that performs a write as a side effect of what looks like a read (compaction on
open, lazy index build on first query); a test helper that mutates a target being reused inside
the package for convenience.

**Mitigation:** five independent layers per [ADR-0001](adr/0001-read-only-by-default.md) —
structural (no write methods on the protocol), static (`P0-09` AST guard), session-level
(server-enforced read-only transactions), empirical (`P5-07`, `P8-10` hash and mtime harness plus
read-only mounts), and documented (`SECURITY.md` treats it as a vulnerability).

**If it happens:** immediate yank of the affected release from PyPI, a public post-mortem, and a
full audit of every adapter. Transparency is the only recoverable response.

---

## R2 — Uncalibrated thresholds cause false alarms {#r2}

**Consequence:** the check gets `|| true`-d in the pipeline, or removed entirely. A disabled check
protects nothing, so this quietly nullifies the whole project.

This is the **most likely** significant risk. The inherited thresholds have no published
measurement behind them, and at least three of the five are known to be dataset-dependent.

**Triggers to watch:** early issues titled "false positive"; users reporting `FAIL` on an index
they know is healthy; hubness complaints from high-dimensional corpora.

**Mitigation:** `P8-01` measures healthy ranges across reference corpora and publishes sensitivity
curves; `P8-02` calibrates defaults with documented false-positive rates; `P8-03` adds
baseline/delta gating for corpora the defaults do not fit; every report states which thresholds
were applied. Guard rails against the wrong fix: **do not tune until the warnings stop** —
some corpora are genuinely pathological ([ADR-0011](adr/0011-thresholds-and-baseline-mode.md)).

**If it happens:** treat false-positive reports as calibration data, not nuisances. Publish
revised profiles quickly (`P9-08`). A fast, evidence-based response to the first few reports is
what converts complainants into contributors.

---

## R3 — A metric is silently wrong {#r3}

**Consequence:** critical and insidious. Users make production decisions on our numbers. A metric
that is wrong in a plausible-looking way may never be caught by a user, because they have nothing
to check it against — which is the entire reason they installed the tool.

**Triggers to watch:** an oracle test being skipped or loosened; a metric implemented without a
naive reference; a threshold comparison mutant surviving; disagreement between engines on an
intrinsic metric.

**Mitigation:** the whole testing strategy exists for this. Naive oracles for every metric
(`P2-03`); differential and block-size-invariance testing (`P2-04`); hand-verified fixtures A, B
and C; property invariants; mutation testing with zero survivors permitted in threshold logic
(`P8-07`); cross-engine consistency on intrinsic metrics (`P7-07`), which is the only check that
would catch an adapter-level enumeration or normalisation bug.

Specific known-dangerous spots, each with a dedicated test: `float16` accumulation
([ADR-0005](adr/0005-ground-truth-precision-and-blocking.md)), unclamped negative squared
distances producing `nan`, top-`k` merge across block boundaries, `ceil(0.01·S)` off-by-one, and
`ddof` in the CV.

**If it happens:** yank, fix, publish a correction with the range of affected versions and the
direction of the error, and add the regression test before the release.

---

## R4 — Engine API drift {#r4}

**Consequence:** adapters break on new engine versions; users get errors on install. Manageable
but a steady maintenance tax.

**Triggers:** a new major version of Lance, Qdrant, or pgvector; a deprecation warning appearing
in test output.

**Mitigation:** tested version ranges declared per extra (`P5-08`); a runtime warning (once, not
per call) when outside the range; nightly CI installing the newest release of each SDK so drift is
found before users find it; capability probes that degrade to `UNAVAILABLE` rather than crashing;
the guardrail that no agent codes against a remembered API.

**If it happens:** the nightly job files an issue. Patch release with a widened or corrected
range.

---

## R5 — Ground truth cost at real scale {#r5}

**Consequence:** users with 10M+ vectors find the tool impractical and leave.

**Triggers:** issues about audit duration or memory; users reporting OOM.

**Mitigation:** the ~1M × 768 ceiling is declared honestly up front rather than discovered;
blocked BLAS keeps memory bounded ([ADR-0005](adr/0005-ground-truth-precision-and-blocking.md));
`--max-seconds` and `--max-memory-mb` degrade to documented sampling with an explicit `truncated`
flag rather than being OOM-killed (`P8-05`); published measured performance numbers so users can
predict cost before running (`P8-04`).

**If it happens:** sampling with a bootstrap confidence interval is already compatible with
[ADR-0003](adr/0003-empirical-metrics-only.md) — it resamples measurements rather than assuming a
distribution. GPU acceleration is a P10 candidate, with the caveat that it changes the determinism
guarantee.

---

## R6 — Inconsistent reads of a live index {#r6}

**Consequence:** slightly wrong numbers, or a crash mid-audit. Likely to occur in normal
production use, since the whole point is auditing live systems.

**Mitigation:** version pinning eliminates it entirely for LanceDB (`P5-02`) — worth advertising
as a reason LanceDB audits are the most trustworthy; `snapshot_inconsistent` warnings elsewhere
with counts of what shifted; the chaos suite (`P8-06`) asserts no crash and no silent wrongness
under concurrent writes and compaction; vanished IDs are tolerated and counted rather than
crashing.

**If it happens:** it is reported, not hidden. A number with a stated caveat is useful; a number
that quietly averaged over a moving target is not.

---

## R7 — Scope creep prevents shipping {#r7}

**Consequence:** high likelihood, high impact. The specification describes three adapters, five
metrics, a CLI, a Prometheus exporter, a FastAPI server and a WebGL visualizer. That is a large
surface, and every item on it is interesting.

**Triggers:** work starting on a P10 item; a phase gate being declared passed with unchecked
boxes; "while I'm in here" commits; a fourth engine being added before the third is tested.

**Mitigation:** phase gates are executable commands, not judgements
([`03-phases-overview.md`](03-phases-overview.md)); out-of-scope items are enumerated explicitly
([`00-vision-and-scope.md §5`](00-vision-and-scope.md)) and parked in
[P10](phases/phase-10-post-1.0-horizon.md) with their blockers recorded; the agent playbook
forbids exceeding a ticket's scope; the MVP gate is a concrete checklist.

**If it happens:** cut adapters before cutting quality. A tool that audits one engine correctly is
worth more than one that audits four unreliably.

---

## R8 — Credential or data leak {#r8}

**Consequence:** high. Reports get pasted into public issue trackers, and screenshots get posted
on social media.

**Mitigation:** a redaction filter on every log handler and on `TargetDescriptor.location`
(`P0-06`), applied by default with no flag to disable; a test that audits a corpus seeded with a
recognisable secret and greps the serialised report; scene payloads carry opaque integer IDs only,
never text or metadata; label cardinality bounded in Prometheus output; zero-egress verification
in both the Python package and the web bundle (`P8-10`).

**If it happens:** treat as a security issue with a coordinated disclosure, not a bug.

---

## R9 — Visualizer cannot handle target scale {#r9}

**Consequence:** the showcase half of the value proposition fails, and the README GIF is the first
thing anyone sees.

**Mitigation:** binary transport and class-stratified LOD from the start
([ADR-0009](adr/0009-scene-transport-and-lod.md)); a single draw call with zero per-frame
allocation; progressive loading with findings in the first chunk; a measured display budget
default rather than an optimistic one; a hard guard that refuses a budget the device cannot
support instead of hanging the tab; geometry disposal leak tests.

**If it happens:** lower the default budget. Fidelity of the picture is negotiable; the metric
numbers in the HUD are not.

---

## R10 — Anchor issues fixed or misrepresented at launch {#r10}

**Consequence:** the launch narrative collapses, or an upstream maintainer objects publicly to an
unfair characterisation of their project. The second is worse than the first.

**Mitigation:** `P9-04` requires re-verifying all four anchor issues with a recorded check date
before publishing; reproduction tests assert the pathology independently, so a fixed issue is
detected as a test change rather than as a launch-day surprise; the framing is "the industry
under-instruments this class of failure", not "these engines are broken", because every one of
these engines made a defensible trade-off; upstream fixes are credited.

**If it happens:** update the docs and reframe. A fixed upstream issue is genuinely good news and
should be reported as such — the reproduction test then becomes a regression guard, which is a
better story than the original complaint.

---

## R11 — No adoption {#r11}

**Consequence:** the work exists and nobody uses it.

**Mitigation:** `uvx vhecfsck demo` with no database requirement, so trying it costs nothing; a
GIF that shows the failure rather than the tool; CI recipes that make integration copy-pasteable
(`P9-03`); Prometheus output so it fits existing dashboards; measured numbers rather than claims;
an honest limitations section, which for a technical audience builds more credibility than any
feature list.

**If it happens:** the tool is still a strong portfolio artifact and a genuine contribution to a
real gap. But diagnose before concluding: no adoption because nobody heard, because installation
was hard, or because the problem is not felt, are three different problems with three different
responses.

---

## R12 — Flaky integration tests {#r12}

**Consequence:** a red build that gets ignored, which means the next real failure also gets
ignored.

**Mitigation:** pinned container images; health-gated startup instead of `sleep`; skips treated as
failures in CI so nothing merges accidentally unverified; visual regression in a pinned container
with a tolerance measured from actual variance rather than guessed; ten-consecutive-run stability
required before a visual baseline is accepted; probabilistic reproductions (likely for
`qdrant#7147`) documented as probabilistic with a measured rate rather than presented as
deterministic.

**If it happens:** quarantine and fix within a defined window, or delete. A permanently
quarantined test is worse than no test because it consumes attention while protecting nothing.

---

## R13 — Reference dataset licensing {#r13}

**Consequence:** a licence violation in the calibration data, or the inability to publish the
calibration results.

**Mitigation:** `P8-01` records licence and provenance for every dataset in
`docs/calibration/datasets.md`, prefers permissively licensed corpora, downloads on demand rather
than redistributing, and publishes derived statistics rather than data.

---

## R14 — Maintainer burden from adapters {#r14}

**Consequence:** adapters rot, the capability matrix becomes fiction, and the project's core claim
of honesty erodes.

**Mitigation:** [P10](phases/phase-10-post-1.0-horizon.md) gates new adapters on demonstrated
demand rather than enthusiasm; the contract suite makes a third-party adapter a bounded and
reviewable contribution; nightly drift detection surfaces rot early; three well-tested engines is
an explicitly better outcome than eight aspirational ones.

**If it happens:** mark an adapter unmaintained and say so in the capability matrix, rather than
letting users discover it. An honest "unmaintained" label costs less credibility than a silently
broken adapter.
