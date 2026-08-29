# ADR-0012 — Canonical name `vhecfsck`

**Status:** Accepted, with one open question for the owner
**Affects:** everything user-facing

## Context

The source architecture blueprint named the tool `vecfsck` — a transparent contraction of
"vector" plus `fsck`. The project owner renamed it to `VHECFSCK`, and specified that the correct
form is lowercase: `vhecfsck`.

A name needs to be settled before the first commit, because it appears in the package name, the
CLI binary, the PyPI project, the import path, the Prometheus metric prefix, and every document.
Renaming after a PyPI release is possible but leaves a permanent trail of dead references and
broken installs.

## Decision

**`vhecfsck`, lowercase, everywhere it is a technical identifier:**

- Python package: `vhecfsck`
- CLI binary: `vhecfsck`
- PyPI project: `vhecfsck` — verified available (a `404` from `pypi.org/pypi/vhecfsck/json` at
  planning time) and reserved in `P0-13`
- Repository: `vhecfsck`
- Prometheus metric prefix: `vhecfsck_`
- Config file: `vhecfsck.toml`; env prefix: `VHECFSCK_`
- Environment/API namespaces: lowercase throughout

`VHECFSCK` in capitals is acceptable in prose, document titles, and headings. It is never used
as an identifier.

No alias, no `vecfsck` shim, no shorter alternative binary. One name, spelled one way. A test in
`P9-06` greps the repository for stray `vecfsck` occurrences, since the source specification uses
the old spelling throughout and transcription errors are near-certain.

## Open question for the owner

**What does the `H` stand for in public-facing copy?**

This is not a technical blocker — the identifier is settled — but it blocks the README, and it
cannot be resolved by inference. Nothing in the source material explains the added letter, and
inventing an expansion would be a fabrication baked into the project's front door.

The plausible readings, for the owner to choose from or override:

| Reading | Expansion | Pronunciation |
| :--- | :--- | :--- |
| Health | **V**ector **H**ealth ch**EC**k + `fsck` | "vee-aitch-e-see-fisk" or "vector health check" |
| Health, alternative gloss | **V**ector **HE**alth **C**heck + `fsck` | "vee-heck-fisk" |
| No expansion | Just a name, deliberately unexplained | as spelled |

"Health" fits the product thesis precisely — the tool is a health diagnostic, and the
`smartctl` analogy in the vision document reinforces it. It is the recommended reading, but the
owner should confirm rather than have it assumed.

**Resolve before `P9-01` (README).** Until then, documentation refers to the tool only as
`vhecfsck` with no expansion, which is a valid interim state. Record the answer as an amendment
to this ADR.

## Consequences

**Buys:** one unambiguous name across every surface, claimed early on both GitHub and PyPI.

**Costs:**
- `vhecfsck` is hard to type and hard to say out loud, and the `h` will be dropped in searches
  and in conversation. Mitigation: the README should mention "vector index health check" and
  "vector fsck" in prose so search engines connect the concept to the name.
- Someone could squat `vecfsck` on PyPI, currently also free. Reserving it as a defensive
  redirect is an option worth considering in `P0-13`, though it also risks confusing users about
  which is canonical. Owner's call.

## Alternatives considered

- **Reverting to `vecfsck`.** Rejected: the owner specified `vhecfsck` explicitly.
- **A short alias binary (`vfsck`, `vhc`).** Rejected: two names for one tool splits
  documentation, muscle memory and search results. Shell aliases are the user's business.
- **A friendlier, unrelated name.** Rejected: `fsck` is the analogy that makes the tool
  immediately legible to the SRE audience, and it is doing real work in the name.

## Revisit if

Never for the identifier. The public expansion of `H` is amended here once the owner decides.
