# GIT AND VERSION CONTROL WORKFLOW (Gitstuff)

Follow these rules for committing code, running hooks, and maintaining version safety.

---

## 1. GIT METADATA BLOCK

Upon successful completion of a logical task, always append a dedicated Git Metadata block at the absolute end of your response using the following format:

<!-- agents-md:begin commit -->
One commit per logical task, conventional message:

```yaml
Branch Name: <type>/<short-descriptive-name>  # e.g. feat/provider-fallback
Commit Message: <type>(<scope>): <short description in present tense>
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`. The body
says **why**, not what — the diff already says what.
<!-- agents-md:end commit -->

---

## 2. PRE-COMMIT HOOK CONVENTIONS

To keep code quality and formatting consistent before any commit is finalized, use the Python **`pre-commit`** framework (configured via a `.pre-commit-config.yaml` at the workspace root). This replaces Node-centric tooling (Husky / lint-staged) for Python projects.

A ready-to-use base config ships with this protocol at [`templates/.pre-commit-config.yaml`](./templates/.pre-commit-config.yaml) — copy it to the workspace root and pin the `rev:` tags.

### 2.1. Recommended Hook Setup
Conventions (swappable per app, but stay consistent within a repo):
- **Format + Lint**: `ruff format` and `ruff check --fix` on staged files (fast, autofixing).
- **Secret Scan**: a secret-detection hook (e.g. `detect-secrets` / `gitleaks`) to enforce the "no keys in git" rule from [SKILL.md](./SKILL.md) §3.2.
- **Hygiene**: trailing-whitespace, end-of-file-fixer, TOML/YAML/JSON validity, a large-file guard, and a check that `.env` is never staged.
- **Static guards**: the repo's own AST guards — the same commands `make verify` runs under `guards` ([guardrails.md](./guardrails.md) §5). They are fast and they protect the invariants that matter most, so they belong on the commit path, not only in CI.

**Deliberately excluded: type checking and the test suite.** Not because they are unimportant — they are in the gate ([guardrails.md](./guardrails.md) §1) and in CI. The reason is behavioural: a hook slow enough to be annoying gets bypassed with `--no-verify`, and a bypassed hook protects nothing. Keep the commit path fast so nobody learns the habit of skipping it. If you want the type check available locally, wire it as a `manual`-stage hook.

### 2.2. Installation & Smoke Testing
- Install the git hook once per clone: `uv run pre-commit install`.
- Always smoke-test locally before pushing or resolving a task: `uv run pre-commit run --all-files`.
- For a JS/TS frontend that exists alongside (see [SKILL.md](./SKILL.md) §3.3), wire its own formatter via that ecosystem's tooling; do not impose Python hooks on JS files or vice versa.

---

## 3. GIT DELIVERY & AUTOMATION POLICY

The agent **owns the full git lifecycle and executes it automatically** — branch, stage, commit, push, and merge to the base branch — gated by a single mandatory human checkpoint. Push and merge are **allowed**; they are not blocked.

### 3.1. The Approval Gate (mandatory)
<!-- agents-md:begin delivery -->
- Branch, stage and commit **locally** as freely as you like while working.
- **On delivery:** squash those local commits into **one** conventional commit, then merge to
  `main` (or the repo's base). Only after an **explicit go-ahead** ("ok", "dale", "andá",
  "mergealo"). Silence, a thumbs-up on something unrelated, or the absence of objection is
  **not** approval.
- **Never `git push` and never merge to the base branch** until that go-ahead exists.
- Reporting "ready to test" and then **waiting** is mandatory, not optional politeness.
<!-- agents-md:end delivery -->

### 3.2. Delivery Sequence (run only after approval)
Default sequence once the user approves:
1. Confirm you are on the dedicated task branch (`<type>/<short-name>`). Create it now only if the work was never branched.
2. Stage **only files relevant to the task**. Leave unrelated untracked/modified files alone; if scope is unclear, ask (see §3.3).
3. **Squash** the branch onto one conventional commit (`git reset --soft` to the merge-base with `<base>`, then one `git commit` using the metadata format from §1, ending with the `Co-Authored-By` trailer). Soft reset is the squash tool — it is not `reset --hard`. If the branch was already pushed, squash + update needs a force-push: **stop and ask** (§3.3 / §3.4).
4. `git push -u origin <branch>` (or the agreed force-push after the user said yes).
5. `git checkout <base>` → `git merge --no-ff <branch>` → `git push origin <base>`. (`<base>` is usually `main`.)
6. *(Optional, ask first)* delete the merged branch locally and on the remote.

> Alternative: if the repo works through pull requests, substitute steps 4–5 with `gh pr create` + merge. Default to the direct merge above unless the user or repo conventions say otherwise.

### 3.3. Stop-and-Ask Conditions ("when it gets complicated")
**Pause and ask the user** before continuing if any of these arise during delivery:
- Merge conflicts, or the base branch has diverged / moved since branching.
- `make verify` is **red** — including "red for a reason that predates my change". Delivering on top of a red gate makes the next person's failure indistinguishable from yours.
- A pre-commit hook, type check, test, or CI check **fails**.
- The base branch is **protected**, or the push is rejected.
- A **force-push** (`--force` / `--force-with-lease`) would be required.
- Commit **scope is ambiguous** (unrelated changes staged, or unrelated untracked files present that might belong in the commit).
- The remote, credentials, or target branch are **not what was expected**.

### 3.4. Destructive Commands (always require explicit confirmation)
These are **not** part of the normal flow and risk irreversible data loss. Never run them autonomously — propose the command and get an explicit "yes" first:
- `git reset --hard` (prefer a soft reset or `git restore <file>`).
- `git clean -f` / `git clean -fd`.
- `git branch -D`.
- `git checkout .` / `git restore .` (reverting the entire working directory).
- Any history rewrite on an already-pushed branch (`rebase`, `commit --amend` after push, force-push).

### 3.5. Claude Code Integration
Optionally register a `PreToolUse` matcher hook (e.g., `.claude/hooks/block-dangerous-git.sh`) that intercepts **only the §3.4 destructive commands**. `git push` and `git merge` must **not** be blocked — they are governed by the approval gate (§3.1), not by a hook.
