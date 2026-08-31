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
        coverage layers readonly mutation web-build web-test web-test-e2e demo demo-gif calibrate clean clean-proc

help:  ## show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- The gate ----------------------------------------------------------------

verify: clean-proc lint format-check typecheck coverage layers readonly clean-proc  ## THE GATE — once per ticket (coverage is the suite)

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

test: clean-proc  ## inner-loop suite (no cov); not a verify prerequisite
	uv run pytest -m "not ($(SLOW_MARKS))" --no-cov

test-fast:  ## the fast suite without coverage instrumentation
	uv run pytest -m "not ($(SLOW_MARKS))" --no-cov -q

coverage: clean-proc  ## two floors from one run: whole tree (≥80), then core/ (≥90)
	uv run pytest -m "not ($(SLOW_MARKS))" --cov=$(PKG) --cov-report=term-missing --cov-report=xml --cov-fail-under=$(COV_ALL) -q
	uv run coverage report --include='$(CORE)/*' --fail-under=$(COV_CORE)

layers:  ## import-layering contracts (P0-08)
	uv run lint-imports

readonly:  ## AST read-only guard (P0-09 / ADR-0001)
	uv run python scripts/check_readonly.py

mutation:  ## mutation testing (stub until a later phase owns it)
	@echo "mutation: deferred (stub ok)"

web-build:  ## front-end bundle (P4-11)
	@if command -v npm >/dev/null 2>&1; then \
		npm --prefix vhecfsck/web run build; \
	else \
		echo "npm not installed; skipping web-build"; \
	fi

web-lint:  ## front-end lint and typecheck (P4-07)
	@if command -v npm >/dev/null 2>&1; then \
		npm --prefix vhecfsck/web run typecheck; \
	else \
		echo "npm not installed; skipping web-lint"; \
	fi

web-test:  ## front-end unit tests (P4-07)
	@if command -v npm >/dev/null 2>&1; then \
		npm --prefix vhecfsck/web test; \
	else \
		echo "npm not installed; skipping web-test"; \
	fi

web-test-e2e:  ## front-end e2e browser tests via Playwright
	@if command -v npm >/dev/null 2>&1; then \
		npm --prefix vhecfsck/web run test:e2e; \
	else \
		echo "npm not installed; skipping web-test-e2e"; \
	fi

demo:  ## local demo scenario (P3-05)
	uv run vhecfsck demo

demo-gif:  ## deterministic README GIF (P6-07)
	uv run python scripts/record_demo.py

calibrate:  ## P8-01 reference calibration (downloads public corpora on demand)
	uv run python scripts/calibrate.py --profile reference --out docs/calibration

clean:  ## remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

clean-proc:  ## kill orphaned pytest processes for this checkout
	uv run python scripts/clean_orphans.py
