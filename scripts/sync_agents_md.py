#!/usr/bin/env python3
"""Generate the repo-root AGENTS.md from the dev-protocol skill.

AGENTS.md is read automatically by most agents on every session; a skill module is read
only if the agent chooses to follow a pointer. So the prohibitions are copied inline and
everything else stays a pointer. See dev-protocol/guardrails.md §6.

The copy is GENERATED, which is what keeps "one source of truth" intact: the source is
guardrails.md, and `--check` fails the build the moment the copy drifts. Hand-maintained
duplication drifts; generated duplication cannot.

Usage in a new app:
    1. Copy to `scripts/sync_agents_md.py`.
    2. Point SKILL_DIR at wherever the skill lives in this repo.
    3. Generate:  uv run python scripts/sync_agents_md.py
    4. Verify:    uv run python scripts/sync_agents_md.py --check   (wired into `make verify`)

Exit codes follow dev-protocol/code-design.md §4:
    0 OK · 2 FAIL (drift, or output over the line budget) · 4 USAGE (bad arguments)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# =============================================================================
# CONFIG — the only part you edit per repo
# =============================================================================

SKILL_DIR = Path(".agents/skills/dev-protocol")
AGENTS_PATH = Path("AGENTS.md")

# AGENTS.md is paid for on every session, so length is a real cost.
MAX_LINES = 80

# =============================================================================

MARKER = "agents-md"
OK, FAIL, USAGE = 0, 2, 4

HEADER = f"""<!-- GENERATED FILE — DO NOT EDIT BY HAND.
     Source: {SKILL_DIR}/guardrails.md and git-workflow.md
     Regenerate: uv run python scripts/sync_agents_md.py
     Verified by `make verify`; editing this file directly will fail the gate. -->
"""


def extract(path: Path, name: str) -> str:
    """Return the text delimited by <!-- agents-md:begin NAME --> ... :end NAME -->."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"<!--\s*{MARKER}:begin\s+{name}\s*-->\n(?P<body>.*?)\n<!--\s*{MARKER}:end\s+{name}\s*-->",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"{path}: missing `{MARKER}:begin {name}` block")
    return match.group("body").strip("\n")


def render() -> str:
    guardrails = SKILL_DIR / "guardrails.md"
    git_workflow = SKILL_DIR / "git-workflow.md"

    return f"""{HEADER}
# Agent operating rules

The full protocol lives in [`{SKILL_DIR}/SKILL.md`]({SKILL_DIR}/SKILL.md). The rules below
are copied here because they must apply even if you never open it.

## The gate

{extract(guardrails, "gate")}

## Hard guardrails

Violating one of these means the work is wrong **regardless of whether the tests pass**.

{extract(guardrails, "guardrails")}

## Delivery

{extract(git_workflow, "delivery")}

{extract(git_workflow, "commit")}

## Everything else

Read [`SKILL.md`]({SKILL_DIR}/SKILL.md) first (role, style, environment, idea-to-delivery
flow). Open a module only when the task calls for it:

| Task | Module |
| :--- | :--- |
| design, TDD, error contract | `code-design.md` |
| a bug or a red test | `debugging.md` |
| verifying, closing, installing a guard | `guardrails.md` |
| reviewing a diff, filing issues | `qa-review.md` |
| committing, hooks, delivery | `git-workflow.md` |
| a contract or doc changed | `documentation.md` |
| arriving cold, designing from scratch, debug Phase 3 | `lessons-learned.md` |

Hard toolchain rule: Python dependencies go through `uv`. Never `pip install`, never a
manually activated venv.
"""


def main(argv: list[str]) -> int:
    check_only = False
    for arg in argv:
        if arg == "--check":
            check_only = True
        else:
            print(__doc__, file=sys.stderr)
            return USAGE

    if not SKILL_DIR.is_dir():
        print(f"sync_agents_md: skill not found at {SKILL_DIR}", file=sys.stderr)
        return USAGE

    generated = render()
    line_count = len(generated.splitlines())
    if line_count > MAX_LINES:
        print(
            f"sync_agents_md: generated AGENTS.md is {line_count} lines, budget is {MAX_LINES}. "
            f"Shorten the source blocks in {SKILL_DIR}/guardrails.md.",
            file=sys.stderr,
        )
        return FAIL

    current = AGENTS_PATH.read_text(encoding="utf-8") if AGENTS_PATH.exists() else None

    if check_only:
        if current == generated:
            print(f"AGENTS.md: in sync ({line_count} lines).")
            return OK
        print(
            "AGENTS.md has drifted from the skill (or does not exist).\n"
            "Do not edit AGENTS.md by hand — edit guardrails.md, then run:\n"
            "  uv run python scripts/sync_agents_md.py",
            file=sys.stderr,
        )
        return FAIL

    if current == generated:
        print(f"AGENTS.md: already up to date ({line_count} lines).")
        return OK

    AGENTS_PATH.write_text(generated, encoding="utf-8")
    print(f"AGENTS.md: regenerated ({line_count} lines).")
    return OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
