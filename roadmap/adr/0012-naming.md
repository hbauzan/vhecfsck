# ADR-0012 — Canonical name `vhecfsck`

**Status:** Accepted. Public-copy question resolved 2026-09-02 (H = Hector, wordplay).
**Affects:** everything user-facing

## Reservation status (P0-13)

Recorded at P0-13 execution (do not pretend these were always true):

| Surface | Status at P0-13 |
| :--- | :--- |
| GitHub `hbauzan/vhecfsck` | Reserved. Remained **PRIVATE** until the owner flipped visibility. |
| PyPI `vhecfsck` | Name still free (`404` from `pypi.org/pypi/vhecfsck/json` at execution). |
| `pyproject.toml` URLs | Homepage / Repository / Issues / Changelog filled pointing at the GitHub repo. |

**Amendment (2026-09-02).** GitHub is **public** (P9-07). PyPI `vhecfsck` **0.1.3** is
published. Trusted Publishing is live (P9-12: env `pypi`, workflow filename `release.yml`).
Do not add a PyPI secret. Do not cut `v0.1.3` again (PyPI will not re-accept that version).
Tags and publishes remain owner-gated (lesson 68).

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

## Public copy (resolved 2026-09-02)

**What the `H` is:** the author's given name, **Hector**. The name is a personalized play on
Unix `fsck` (a vector-index checker), not an acronym.

Owner decision (hbauzan, 2026-09-02). Do **not** publish "Vector Health check",
"Vector HE-alth Check", or any other expansion invented to fill the letter. Those readings
were speculation in the original draft of this ADR; they are not the gloss.

Public-facing copy (README, docs home) states that fact in one sentence. Technical identifiers
stay lowercase `vhecfsck`. No alias binary. `VHECFSCK` remains acceptable in headings only.

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

Never for the identifier. Never for the public gloss of `H` — that is closed. Do not reopen
it to pick Health or to invent a different expansion.
