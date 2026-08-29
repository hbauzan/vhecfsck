# Release Plan

Covers versioning, packaging, publication, and what "stable" means for each surface. Detailed
launch execution lives in [P9](phases/phase-9-docs-release-and-launch.md).

---

## 1. Versioning and stability contracts

SemVer, starting at `0.1.0`. The `0.x` prefix would normally mean nothing is stable, which is not
true here — some surfaces are depended upon by CI pipelines from the first release and must be
stable regardless of the leading zero. So the guarantees are stated per surface rather than
inferred from the version number.

| Surface | Stability from `0.1.0` | Change policy |
| :--- | :--- | :--- |
| **Exit codes** | Stable | Additions only, in a minor release. Never a change of meaning. |
| **Report JSON schema** | Stable, independently versioned | [ADR-0008](adr/0008-report-schema-versioning.md): additive → minor `schema_version`; breaking → major plus a migration note and a conversion utility. |
| **Prometheus metric names and labels** | Stable | Renames require a deprecation period emitting both names. Dashboards break silently otherwise. |
| **CLI command names and documented flags** | Stable | Additions freely; removals need a deprecation cycle with a warning. |
| **Python API** (`vhecfsck.*`) | **Unstable** | May change in any minor release. Documented as such; the CLI and the report are the supported interfaces. |
| **Metric definitions and default thresholds** | Semi-stable | A definition change is breaking and bumps `schema_version`. A *threshold* change is a minor release with the before/after values in the changelog, since it changes verdicts on unchanged data. |
| **Scene payload format** | Unstable | Internal transport between our server and our front end, shipped together. |

Threshold changes deserve emphasis: changing a default flips verdicts on data that did not change,
which from the user's perspective is indistinguishable from a bug. Every such change is called out
prominently, never bundled into a routine release note.

`1.0.0` when: three adapters are stable, thresholds are calibrated with published evidence, the
report schema has survived real-world use without a breaking change, and the Python API is ready
to be committed to.

---

## 2. Packaging

Per [ADR-0002](adr/0002-packaging-and-toolchain.md).

- **Backend:** `hatchling`. Version single-sourced in `pyproject.toml`.
- **Base install:** `numpy` + `typer`. Extras: `[lancedb]`, `[qdrant]`, `[postgres]`, `[server]`,
  `[dev]`, `[all]`.
- **Front end bundled:** the Hatch build hook runs the Vite build and includes `web/dist` in both
  the wheel and the sdist, so no user ever needs Node
  ([ADR-0010](adr/0010-frontend-build-and-bundling.md)).
- **Artifacts:** one pure-Python wheel (`py3-none-any`) plus an sdist containing the prebuilt
  bundle.
- **The constraint that must be verified every release:** `uvx vhecfsck demo` works on the base
  install with no engine SDK, no server extra, and no Node.

---

## 3. Release pipeline

Tag-triggered, fully automated, with one non-negotiable step in the middle.

```text
git tag v0.1.0
      │
      ├─ make verify-full                     (lint, types, all tests, perf, mutation)
      ├─ build wheel + sdist                  (includes web/dist)
      ├─ publish to TestPyPI
      ├─ install from TestPyPI into a clean container, run `vhecfsck demo`   ← the gate
      ├─ publish to PyPI                      (Trusted Publishing / OIDC)
      ├─ sign artifacts                       (Sigstore attestation)
      ├─ create GitHub release                (notes, SBOM, artifacts)
      └─ deploy docs                          (GitHub Pages)
```

The TestPyPI install-and-smoke step is the only thing that catches a broken wheel — a missing
`web/dist`, a bad entry point, a forgotten dependency — and it catches it before users do. It is
not optional and not skippable under time pressure.

**Credentials:** PyPI Trusted Publishing via OIDC. No long-lived API tokens exist anywhere in the
repository or its secrets. Verified in `P8-11`.

**Changelog:** keep-a-changelog format, assembled from conventional commits, with human editing
allowed before the tag. Every entry says what changed for the *user*, not what changed in the code.

---

## 4. Performance numbers to publish

`P8-04` measures these on a named reference machine whose specification is published so users can
scale the expectation. Every cell is a measurement; none is an estimate. Any number that ships
without having been measured is a liability at launch
([`agent-playbook.md §2`](agent-playbook.md), guardrail 11).

| Scenario | Metric to publish |
| :--- | :--- |
| 100k × 768, `Q=200`, `k=10` | Wall time, peak RSS |
| 1M × 768, `Q=200`, `k=10` | Wall time, peak RSS |
| Hubness, `S=20k`, `d=768` | Wall time, peak RSS |
| Projection, 1M × 768 → 3D | Wall time, peak RSS |
| Full audit, 1M × 768 | Wall time, peak RSS, per-stage breakdown |
| Scene encode, 1M points | Wall time, payload bytes |
| Visualizer, 200k points | Sustained frame rate, GPU tier tested |

---

## 5. Distribution channels

**At launch:**
- PyPI — the primary channel. `uvx vhecfsck` and `pip install vhecfsck`.
- GitHub releases — artifacts, SBOM, attestations.
- A GitHub composite action in-repo (`P9-03`), so CI adoption is a five-line copy-paste.

**Deliberately deferred:**
- A container image. Only worth it once someone asks for a Kubernetes `CronJob` deployment; the
  textfile-collector recipe covers the need without a second artifact to maintain.
- `conda-forge`, Homebrew, Linux distribution packages. Community-driven if demand appears; each is
  a maintenance obligation.

---

## 6. Post-release operations

**Patch releases (`0.1.x`):** bug fixes, adapter compatibility, documentation. Shipped quickly —
responsiveness in the first week after launch determines whether early adopters become
contributors.

**Minor releases (`0.x.0`):** new adapters, new metrics, new features. Threshold changes go here,
flagged prominently.

**Yank policy:** yank immediately for a read-only violation (any severity) or a metric correctness
bug that would have changed a user's verdict. Publish the affected version range and the direction
of the error. A silent fix in the next release is not acceptable for a tool people make decisions
with — someone may have already acted on a wrong number and needs to know.

**Deprecation:** anything on a stable surface gets one minor release emitting a warning before
removal, with the replacement named in the warning text.

**Support window:** the current minor release. Backports only for a read-only violation or a
correctness bug.

---

## 7. Pre-release checklist

Run before every tag, not just the first.

- [ ] `make verify-full` green on the release commit.
- [ ] `CHANGELOG.md` complete, with any threshold change called out prominently.
- [ ] `schema_version` correct; committed JSON Schema matches the model.
- [ ] Golden reports regenerated if the schema changed, with the diff reviewed.
- [ ] Docs build clean; link check passes; generated CLI and schema references current.
- [ ] Every published performance number re-measured on this release, not carried over.
- [ ] Engine version ranges verified against current upstream releases.
- [ ] Anchor issue references re-verified (`P9-04`) with the check date recorded.
- [ ] `pip-audit` and `npm audit` clean at high severity.
- [ ] TestPyPI install-and-demo smoke test passed in a clean container.
- [ ] `uvx vhecfsck@<version> demo` verified on a machine that has never had the package
      installed — not on the development machine, where a stale cache can hide a packaging bug.
