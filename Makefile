# =============================================================================
# vhecfsck — single quality gate
# `make verify` is the ONE command that decides whether work is acceptable.
# See roadmap/phases/phase-0-foundation.md (P0-04) and AGENTS.md.
# =============================================================================

PKG  ?= vhecfsck
CORE ?= $(PKG)/core

COV_ALL  ?= 80
COV_CORE ?= 90

# Markers excluded from the default / gate run (P0-03).
SLOW_MARKS ?= slow or integration or perf

.DEFAULT_GOAL := help
.PHONY: help verify verify-full lint format-check fmt typecheck test test-fast \
        coverage layers readonly mutation web-build demo clean

help:  ## show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- The gate ----------------------------------------------------------------

verify: lint format-check typecheck test coverage layers readonly  ## THE GATE — green before every commit

verify-full: verify  ## the gate plus slow suites and mutation (stubs OK until owned)
	@ec=0; \
	uv run pytest -m "$(SLOW_MARKS)" -q || ec=$$?; \
	if [ $$ec -ne 0 ] && [ $$ec -ne 5 ]; then exit $$ec; fi
	@$(MAKE) mutation

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

coverage:  ## two floors: whole tree (≥80), then core/ (≥90)
	uv run pytest -m "not ($(SLOW_MARKS))" --cov=$(PKG) --cov-fail-under=$(COV_ALL) -q
	uv run pytest -m "not ($(SLOW_MARKS))" --cov=$(CORE) --cov-fail-under=$(COV_CORE) -q

layers:  ## import-layering contracts (P0-08)
	uv run lint-imports

readonly:  ## AST read-only guard (P0-09 / ADR-0001)
	uv run python scripts/check_readonly.py

mutation:  ## mutation testing (stub until a later phase owns it)
	@echo "mutation: deferred (stub ok)"

web-build:  ## front-end bundle (deferred to P4)
	@echo "web-build: deferred to P4 (stub ok)"

demo:  ## local demo scenario (deferred to P3-05)
	@echo "demo: deferred to P3-05 (stub ok)"

clean:  ## remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
