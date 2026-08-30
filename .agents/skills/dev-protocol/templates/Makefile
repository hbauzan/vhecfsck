# =============================================================================
# DEV AGENT PROTOCOL — quality gate template (Python / uv)
# -----------------------------------------------------------------------------
# Usage in a new app:
#   1. Copy this file to the workspace ROOT as `Makefile`.
#   2. Set PKG / CORE below to your package layout.
#   3. Targets whose tooling does not exist yet should be left as stubs that
#      exit 0 — the gate must exist from the FIRST commit, not once the
#      codebase is already messy.
#   4. Run it:  make verify
#
# `make verify` is the ONE command that decides whether work is acceptable.
# An agent must never assemble a verification command from memory.
# See dev-protocol/guardrails.md §1.
# =============================================================================

# Package under test, and the subset holding the actual logic (stricter gate).
PKG  ?= src
CORE ?= $(PKG)/core

# Coverage floors — two gates, not one. See guardrails.md §4.
COV_ALL  ?= 80
COV_CORE ?= 90

# Test selection excluded from the default run. See guardrails.md §4.
SLOW_MARKS ?= slow or integration or perf or live_model

.DEFAULT_GOAL := help
.PHONY: help verify verify-full lint format-check fmt typecheck test test-fast \
        coverage guards agents-sync clean

help:  ## show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- The gate ----------------------------------------------------------------

verify: lint format-check typecheck test coverage guards  ## THE GATE — green before every commit

verify-full: verify  ## the gate plus the slow suites (CI / on demand)
	uv run pytest -m "$(SLOW_MARKS)"

# --- Individual steps --------------------------------------------------------

lint:  ## ruff lint
	uv run ruff check .

format-check:  ## ruff format, check only
	uv run ruff format --check .

fmt:  ## auto-fix formatting and lint
	uv run ruff format .
	uv run ruff check --fix .

typecheck:  ## static type check
	uv run mypy $(PKG)

test:  ## the fast suite
	uv run pytest -m "not ($(SLOW_MARKS))"

test-fast:  ## the fast suite without coverage instrumentation
	uv run pytest -m "not ($(SLOW_MARKS))" --no-cov -q

coverage:  ## two floors from ONE instrumented run: whole tree, then the core
	uv run pytest -m "not ($(SLOW_MARKS))" --cov=$(PKG) --cov-report=term-missing --cov-fail-under=$(COV_ALL) -q
	uv run coverage report --include='$(CORE)/*' --fail-under=$(COV_CORE)

# --- Static guards (guardrails.md §5) ----------------------------------------

guards:  ## provider seam, import layering, AGENTS.md drift
	uv run python scripts/check_provider_seam.py
	uv run lint-imports
	uv run python scripts/sync_agents_md.py --check

agents-sync:  ## regenerate the root AGENTS.md from the skill (guardrails.md §6)
	uv run python scripts/sync_agents_md.py

clean:  ## remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
