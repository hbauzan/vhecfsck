#!/usr/bin/env python3
"""Generate the repo-root AGENTS.md from the dev-protocol skill.

Two adoption modes (guardrails.md §6) — set MODE in CONFIG:

    generated  Project AGENTS.md from skill blocks + optional AGENTS.overlay.md.
               `--check` fails on drift. Default for a new app.

    opt-out    AGENTS.md is hand-written (playbook / product rules). `--check` is
               a no-op. A write attempt is refused so a future agent cannot drop
               product rules by regenerating.

Usage in a new app:
    1. Copy to `scripts/sync_agents_md.py`.
    2. Point SKILL_DIR at wherever the skill lives in this repo.
    3. Set MODE. If generated, optionally add AGENTS.overlay.md for product rules.
    4. Generate (generated mode only):  uv run python scripts/sync_agents_md.py
    5. Verify:    uv run python scripts/sync_agents_md.py --check

Exit codes follow dev-protocol/code-design.md §4:
    0 OK · 2 FAIL (drift, refused write, or over the line budget) · 4 USAGE
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
OVERLAY_PATH = Path("AGENTS.overlay.md")
MODE = "generated"  # "generated" | "opt-out"

# AGENTS.md is paid for on every session, so length is a real cost.
MAX_LINES = 80

# =============================================================================

MARKER = "agents-md"
OK, FAIL, USAGE = 0, 2, 4

HEADER = f"""<!-- GENERATED FILE — DO NOT EDIT BY HAND.
     Source: {SKILL_DIR}/guardrails.md, git-workflow.md, and {OVERLAY_PATH}
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


def overlay_block() -> str:
    if not OVERLAY_PATH.is_file():
        return ""
    body = OVERLAY_PATH.read_text(encoding="utf-8").strip()
    if not body:
        return ""
    return f"\n## Product overlay\n\n{body}\n"


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
{overlay_block()}
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
| arriving cold, designing from scratch, debug Phase 3 | product `lessons-learned.md` (default `roadmap/lessons-learned.md`) |

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

    if MODE == "opt-out":
        if check_only:
            print("AGENTS.md: opt-out mode — not generated; --check is a no-op.")
            return OK
        print(
            "AGENTS.md is opt-out (hand-written playbook / product rules).\n"
            "Refusing to regenerate. Edit AGENTS.md by hand. "
            "See dev-protocol/guardrails.md §6.",
            file=sys.stderr,
        )
        return FAIL

    if not SKILL_DIR.is_dir():
        print(f"sync_agents_md: skill not found at {SKILL_DIR}", file=sys.stderr)
        return USAGE

    generated = render()
    line_count = len(generated.splitlines())
    if line_count > MAX_LINES:
        print(
            f"sync_agents_md: generated AGENTS.md is {line_count} lines, budget is {MAX_LINES}. "
            f"Shorten the source blocks in {SKILL_DIR}/guardrails.md or {OVERLAY_PATH}.",
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
            "Do not edit AGENTS.md by hand — edit guardrails.md or "
            f"{OVERLAY_PATH}, then run:\n"
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
