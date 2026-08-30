# Dev-protocol follow-ups

Queued work on the skill pack and how this repo adopts it. **This is not a
parking lot.** Each row is a pick-up with enough definition to start. It is
also **not** the product critical path (P0–P9) and **not** a miscellaneous
"revisar más adelante" bucket.

Source: the 2026-08-30 protocol review. Items 1–8 of that review are done on
`docs/dev-protocol-hardening`. What remains is below.

Pick one row. Do not "while I was in here" a second.

| ID | Item | Why it is still open | Done when |
| :--- | :--- | :--- | :--- |
| DP-01 | Fold or drop `Por acá va la bocha.md` | One-line pointer; contract already lives in `SKILL.md` §2 | The file is gone, or it is the documented Cursor/IDE ancla and nothing else |
| DP-02 | Language policy for the pack | ELETOR is rioplatense; contract modules are English. Same-name-for-same-concept slips (`gate` / `verify` / definition of done) | One written rule: which language owns which layer, applied to the index |
| DP-03 | Git metadata block vs ELETOR | `git-workflow.md` §1 asks to append a YAML block on every close; ELETOR forbids closing fluff | The block is gone, or it is explicitly "only on delivery", not every reply |
| DP-04 | Cursor user-rule vs protocol commits | Cursor user rules still say "only commit when asked"; the protocol now says local commits are free | The user-rule is aligned, or `AGENTS.md` states which wins in this workspace |
| DP-05 | Domain fit of the skill | The pack describes Python apps that orchestrate LLMs. This product is a read-only CLI auditor | `SKILL.md` §1 names both fits, or a one-line "this repo uses the subset: gate, TDD, approval, ELETOR" |
| DP-06 | When TDD does not apply | DoD seam-escape covers debug-without-seam. Docs, ADR, and one-line chores are still implied-TDD | `code-design.md` lists the cases where TDD is skipped and what replaces it |
| DP-07 | Two-axis review by tool | `qa-review.md` mandates parallel `general-purpose` sub-agents. That is a Claude Code primitive, not a Cursor one | The module branches: Claude Code → two sub-agents; Cursor → two sequential passes in one session |
| DP-08 | `qa-review.md` depth | Still the thinnest module. File-name aliases landed; the review protocol itself did not grow | The module can be followed without inventing a process |
| DP-09 | `USAGE.md` §5 vs portable pack | Workspace-specific notes sit inside the copy-to-another-repo directory | §5 is clearly marked "this workspace only", or it moves to `roadmap/` |
| DP-10 | Role identity in `SKILL.md` §1 | Principal Architect / DevSecOps / high-density copiloto is long and LLM-centric | The role paragraph is one sentence that does not pull an auditor CLI toward Streamlit |

## Out of this list

- Product exit codes (`1` = `WARN`) stay on [ADR-0004](adr/0004-metric-result-states-and-exit-codes.md). The pack default is `8` / `0`+stderr. Do not "align" the CLI.
- Merge-to-`main` on OK is closed. Do not re-open PR-vs-direct as a follow-up unless the user changes it.
