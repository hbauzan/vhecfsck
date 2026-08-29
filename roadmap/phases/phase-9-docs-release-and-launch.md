# P9 — Documentation, Release and Launch

**Goal:** ship `v0.1.0` and give it a fair chance of being found.

Two audiences, two failure modes. The evaluator who bounces because the README does not
immediately show the problem, and the platform engineer who will not install anything near
their production database without evidence. Both have to be served on the same page.

**Entry criteria:** P8 exit checklist complete. Every published number has been measured.

**Exit gate**

```bash
# on a clean machine with no Python packages, no Node, and no database:
uvx vhecfsck@0.1.0 demo
```

---

## P9-01 — README

**Depends on:** P6-07, P8-04 · **Size:** M · **Touches:** `README.md`

**Goal:** the highest-leverage document in the project. Someone decides in fifteen seconds.

**Contract**
- Above the fold: one sentence on what it does, the P6-07 GIF showing green dashboards beside
  a collapsing recall, and the one-line quickstart:
  ```bash
  uvx vhecfsck demo
  ```
- Then, in order: the problem in three sentences with the four anchor issues linked as
  evidence; what the tool measures (the five-metric table with thresholds); the CI recipe with
  exit codes; the engine capability matrix; the read-only guarantee with a link to the
  verification; measured performance numbers; install instructions with extras; a link to the
  docs.
- **Every claim must be independently checkable.** No estimated benchmarks, no rounded-up
  numbers, no "blazingly fast". An infrastructure audience penalises unverifiable claims
  harder than it rewards enthusiasm, and this project's entire pitch is that it reports honest
  numbers.
- State the limitations plainly and early: 3D projection is a lossy sketch; corpus-drawn
  queries give an optimistic recall bound; hubness thresholds are sample-size dependent;
  pgvector DFI is a table-level proxy. Naming your own limits is what makes the rest credible.

**Acceptance criteria**
- [ ] The GIF is under 5 MB and loads on the GitHub repository page.
- [ ] Every number traces to a measurement in `docs/`.
- [ ] The quickstart works verbatim on macOS and Linux from a clean shell.

---

## P9-02 — Documentation site

**Depends on:** P9-01 · **Size:** M · **Touches:** `mkdocs.yml`, `docs/`, `.github/workflows/docs.yml`

**Contract**
- MkDocs Material, deployed to GitHub Pages on release.
- Structure: Getting started · Concepts (what each pathology is and why it is invisible) ·
  Metrics reference (generated from [`02-metrics-spec.md`](../02-metrics-spec.md), which
  remains the single source of truth) · Engine guides · CI integration · Read-only guarantee ·
  Calibration data · Performance · Scenario reproductions · CLI reference (generated from
  Typer) · Report schema reference (generated from the Pydantic model) · Contributing ·
  Architecture decisions (the ADR set).
- CLI reference and schema reference are **generated**, never hand-written. Hand-written
  reference documentation is wrong within two releases.
- A link checker in CI. A dead link in the docs of a reliability tool is an unforced error.

**Acceptance criteria**
- [ ] Docs build with zero warnings; link check clean.
- [ ] Every metric page cites the spec section it derives from.

---

## P9-03 — CI integration recipes

**Depends on:** P3-08 · **Size:** M · **Touches:** `docs/ci-integration.md`, `.github/actions/vhecfsck/`, `examples/`

**Goal:** the retention mechanism. The tool has to be trivial to wire into someone's existing
pipeline, or it gets run once and forgotten.

**Contract**
- Copy-pasteable recipes for: GitHub Actions (including a composite action in this repo),
  GitLab CI, a Kubernetes `CronJob` writing to the Prometheus textfile collector, a plain cron
  entry, and an Airflow/Dagster task.
- Each recipe shows how to handle each exit code — in particular treating `1` (WARN) as a
  non-blocking annotation and `3` (INCONCLUSIVE) as a configuration problem to fix rather than
  an outage to page on.
- A worked alerting example: Prometheus alert rules with sensible `for` durations, plus the
  companion staleness alert on `vhecfsck_metric_unavailable` — because an audit that stopped
  running looks exactly like an audit that is passing.
- A markdown job-summary example using `vhecfsck export --format markdown`.
- Every recipe is smoke-tested in CI where feasible; the composite action is tested against
  the demo scenarios.

---

## P9-04 — Verify the anchor issues and write the launch post

**Depends on:** P5-09, P7-03, P7-05 · **Size:** M · **Touches:** `docs/scenarios/`, `docs/blog/silent-recall-decay.md`

**Goal:** the content that carries the launch, and the fact-check that protects it.

**Contract**
- **Re-verify all four anchor issues** before publishing anything. Check current status, title,
  whether a fix landed and in which version. An upstream maintainer finding a stale or unfair
  characterisation of their project in our launch post is both a credibility problem and an
  avoidable discourtesy. Update
  [`00-vision-and-scope.md §1.4`](../00-vision-and-scope.md) with what is found.
- Write the post around the reproductions: for each, the mechanism, the measured degradation,
  the fact that health checks stayed green, and how the tool detects it. Real numbers from the
  automated reproductions, with the code to reproduce them.
- Frame it as a class of failure the industry under-instruments, not as a list of engines
  behaving badly. Every one of these engines made a defensible engineering trade-off; the gap
  is in observability, which is precisely the gap this tool fills. That framing is both more
  accurate and more likely to be well received by the people whose communities we are about to
  post in.
- Credit upstream fixes where they exist (pgvector v0.8.0 iterative scans, and whatever else
  the re-verification turns up).

**Acceptance criteria**
- [ ] Every issue reference re-verified with the check date recorded.
- [ ] Every number in the post produced by a committed, runnable reproduction.
- [ ] No engine is characterised as broken where the behaviour is a documented trade-off.

---

## P9-05 — Release engineering

**Depends on:** P8-11, P4-11 · **Size:** M · **Touches:** `.github/workflows/release.yml`, `CHANGELOG.md`, `docs/releasing.md`

**Contract**
- Tag-triggered release workflow: `make verify-full` → build wheel and sdist (with the web
  bundle) → publish to TestPyPI → install from TestPyPI into a clean container and run the
  demo → publish to PyPI via **Trusted Publishing / OIDC** (no long-lived API tokens) → create
  the GitHub release with notes, the SBOM, and the artifacts → deploy the docs.
- The TestPyPI install-and-smoke-test step is not optional. It is the only thing that catches
  a broken wheel, and it catches it before users do.
- Version bump in one place; changelog assembled from conventional commits with human editing
  allowed before the tag.
- SemVer with `0.x` semantics stated explicitly: the report schema and exit codes are stable
  contracts from `0.1.0`; Python APIs are not.
- Sigstore attestation for artifacts.

**Acceptance criteria**
- [ ] A dry-run release publishes to TestPyPI and passes the clean-container smoke test.
- [ ] No PyPI token exists anywhere in the repository or its secrets.
- [ ] `pip install vhecfsck` works with no Node toolchain present.

---

## P9-06 — Pre-launch review pass

**Depends on:** P9-01, P9-02, P9-03 · **Size:** M · **Touches:** repository-wide

**Contract**
- A deliberate hostile read of the whole project as an unsympathetic reviewer would perform it:
  - Is any claim in the README unsupported by a measurement?
  - Does any metric have a plausible failure mode we have not documented?
  - Would a database administrator be satisfied by the read-only evidence?
  - Does the tool ever report a number it should have reported as `UNAVAILABLE`?
  - Are the thresholds defensible, and is their calibration published?
  - Does `uvx vhecfsck demo` work on a genuinely clean machine, verified in a fresh container?
- Also: spelling of `vhecfsck` consistent everywhere; no `TODO`, `FIXME` or `XXX` in shipped
  code paths; no stale roadmap references in user-facing docs; licence headers present.
- Findings become tickets and are fixed before the tag, or are explicitly deferred with a
  recorded reason. A known-and-recorded gap is fine; an unknown gap discovered by a stranger in
  a public thread is not.

**Acceptance criteria**
- [ ] Every finding fixed or explicitly deferred with a reason.
- [ ] The demo verified in a fresh container, not on the development machine.

---

## P9-07 — Launch

**Depends on:** P9-04, P9-05, P9-06 · **Size:** M · **Touches:** — (external)

**Contract**
- Tag and publish `v0.1.0`; verify the exit-gate command from a clean machine before announcing
  anything.
- Announce in order: the blog post, then Show HN, then the relevant subreddits, then the
  LanceDB / Qdrant / pgvector community channels — respecting each community's self-promotion
  norms, which differ substantially. Read the room before posting; a rules-violating launch post
  is a permanent first impression.
- Commenting on the upstream anchor issues is acceptable **only** where the tool genuinely helps
  the specific reporter, phrased as a contribution rather than a plug. Drive-by promotion in
  someone else's issue tracker earns lasting ill will and is not worth the clicks.
- Have ready before posting: a maintainer available to answer for several hours, issue
  templates in place, a triage plan, and a prepared honest answer to the two questions that
  will certainly be asked — "how do I know it won't touch my data?" and "where do these
  thresholds come from?"

**Acceptance criteria**
- [ ] Exit gate verified from a clean machine before the announcement.
- [ ] Someone is on hand to respond for the first several hours.
- [ ] Every FAQ answer links to evidence in the docs, not to an assertion.

---

## P9-08 — Post-launch triage window

**Depends on:** P9-07 · **Size:** M · **Touches:** issues, `docs/faq.md`

**Contract**
- A defined window of active triage after launch: respond to every issue, tag false positives
  distinctly from bugs, and keep a running list of the questions people actually ask.
- Expect the largest category to be threshold false positives on corpora unlike anything in
  the calibration set. That is a calibration input, not a nuisance: feed real-world reports
  back into P8-01 and publish revised profiles.
- Build `docs/faq.md` from real questions rather than imagined ones.
- Ship a `0.1.x` patch release for anything blocking a real user, quickly. Responsiveness in
  the first week determines whether early adopters become contributors.

**Acceptance criteria**
- [ ] Every issue in the window triaged.
- [ ] FAQ written from actual questions.
- [ ] Threshold complaints analysed and fed into the calibration data.

---

## P9-09 — Linux port of `setup.sh`

**Depends on:** P0-15, owner "ready to publish" · **Size:** S · **Touches:** `setup.sh`, `tests/e2e/test_setup_sh.py`

**Do not start this ticket until the owner says the project is ready to publish and the
script has been run on a real Linux machine.** A "should work" port from memory is out of
scope. macOS is the only supported console until then.

**Contract**
- Remove the Darwin-only hard stop after a measured Linux run (Ubuntu or Fedora, bash).
- Keep the same menu, exit codes, and Hitchhiker copy. Do not add a daemon, Vite, or a
  hosted-demo publish path.
- `uv` install on Linux uses the official installer, still `[y/N]` on a TTY.
- Tests: the `SETUP_SH_UNAME=Linux` case flips from exit `3` to the same behaviour as
  Darwin. Add a fixture that records the distro and bash version actually used. Do not
  invent a matrix.

**Acceptance criteria**
- [ ] `./setup.sh help` and `./setup.sh sync` succeed on the recorded Linux host.
- [ ] `uv run pytest tests/e2e/test_setup_sh.py` is green on that host and on macOS.

---

## Phase exit checklist

- [ ] `uvx vhecfsck@0.1.0 demo` works on a clean machine, verified in a fresh container.
- [ ] Docs deployed; link check and generated references clean.
- [ ] All four anchor issues re-verified with a recorded check date.
- [ ] Trusted publishing configured; no API tokens; SBOM and attestations attached.
- [ ] CI recipes tested; composite action published.
- [ ] Every README claim traceable to a measurement.
- [ ] Post-launch triage window observed and its findings recorded.
- [ ] Linux `setup.sh` port (`P9-09`) only if the owner has given a publish go-ahead
      and the script was run on a real Linux host.
