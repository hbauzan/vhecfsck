# ADR-0002 — Python floor, uv + hatchling, lean base install

**Status:** Accepted
**Affects:** P0, P9

## Context

The hero command is `uvx vhecfsck demo`, which resolves and installs the package before running
it. Every base dependency is time the evaluator spends staring at a progress bar, and every
transitive dependency is a line a security-conscious infrastructure team reads before allowing
the tool near their database.

At the same time the tool must connect to LanceDB, Qdrant and PostgreSQL, whose SDKs are large
and mutually irrelevant — nobody needs all three.

The development machine runs Python 3.14, but the target audience runs whatever their platform
image ships, which in practice means 3.11 and 3.12 for years to come.

## Decision

- **Python floor 3.11.** Gets `Self`, `LiteralString`, the `tomllib` standard-library parser,
  and exception groups, while remaining installable on realistic production images. CI matrix
  covers 3.11, 3.12 and 3.13 as blocking, with 3.14 as an advisory `continue-on-error` job so
  ecosystem readiness is visible without blocking merges.
- **`uv` for development, `hatchling` as the build backend.** `uv` for speed and a committed
  lock file; `hatchling` because the build hook mechanism is what bundles the compiled front end
  into the wheel (`P4-11`).
- **Base install is `numpy` + `typer` only.** Everything else is an extra:
  `[lancedb]`, `[qdrant]`, `[postgres]`, `[server]` (FastAPI, Uvicorn, Pydantic), `[dev]`, `[all]`.
- **The demo must work on the base install.** No database, no server extra, no dataset. This is
  a hard constraint tested in CI in an environment with no engine SDK present, because it is the
  property most likely to regress silently as someone adds a convenient top-level import.
- **Engine SDKs are imported lazily**, inside adapter factories, so importing the package never
  pulls an SDK and a missing extra produces an actionable install hint rather than an
  `ImportError` traceback.
- **Any new dependency requires an ADR.**

## Consequences

**Buys:** a fast first-run experience, a dependency footprint short enough to be read, and no
possibility that installing the tool for LanceDB drags in a PostgreSQL driver.

**Costs:**
- `pydantic` is in the `[server]` extra, so the report model — which needs it — must either move
  Pydantic into the base install or keep the base report path on dataclasses. **Resolve this in
  `P3-01`:** measure Pydantic v2's install size and import time, and either accept it in the
  base install or keep the core report as dataclasses with Pydantic used only at the API
  boundary. Do not leave the question implicit; it determines whether `demo` stays fast.
- Lazy imports are slightly awkward to type-check and require care to keep out of module scope.
- Optional extras multiply CI configurations.
- Dropping Python 3.10 excludes some older platform images. Accepted: 3.10 reaches end of life
  within the project's relevant horizon.

## Alternatives considered

- **Poetry / PDM.** Fine tools, but `uv` is materially faster and `uvx` *is* the quickstart, so
  aligning the project's tooling with the user's entry point reduces surface area.
- **All engines in the base install.** Rejected: a multi-hundred-megabyte install for a tool
  whose pitch is "run this one command" is self-defeating.
- **Python 3.12 floor.** Rejected as too aggressive for an operations audience.
- **Vendoring engine clients.** Rejected outright: unmaintainable and a supply-chain liability.

## Revisit if

- `uvx` install time for the base package exceeds roughly 10 seconds on a normal connection.
- Python 3.11 falls below meaningful usage in the target audience.
- Pydantic's cost measured in `P3-01` turns out to make the base install untenable, in which
  case record the resolution as an amendment here.
