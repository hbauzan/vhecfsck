# ADR-0010 — Vite + TypeScript, built in CI, bundled in the wheel

**Status:** Accepted
**Affects:** P4, P6, P9

## Context

The visualizer is a Python package's web UI, which creates a genuine tension. Two constraints
pull in opposite directions:

1. **A Python user must never need Node.** `pip install vhecfsck` followed by `vhecfsck serve`
   has to work on a machine with no JavaScript toolchain. Requiring `npm install` at install time
   would disqualify the tool from most of the environments it targets.
2. **The front end must be testable and typed.** The owner's stated requirement is modular work
   with tests at every step. An untyped, untested pile of script tags cannot satisfy that, and the
   renderer contains real logic — buffer decoding, class mapping, LOD accounting — where a silent
   bug produces a plausible-looking but wrong picture.

A third consideration: this is one canvas plus a small HUD panel. Reaching for React or Svelte
would add more build surface and bundle weight than the application code itself.

## Decision

- **Vite + TypeScript in `strict` mode**, with Vitest for unit tests and Playwright for browser
  and visual regression tests. ESLint and Prettier, wired into `make verify` via a `web-lint`
  target so the front end is held to the same gate as the Python.
- **No UI framework.** Three.js, a few hundred lines of DOM for the HUD, and a purpose-built
  canvas helper for the two histograms. Revisit only if the UI genuinely grows.
- **CI builds `vhecfsck/web/dist` and bundles it into both the wheel and the sdist**, via a Hatch
  build hook. `dist/` is a build artifact and is **not committed** to the repository — committed
  build output is a permanent source of merge conflicts and of doubt about whether the shipped
  bundle matches the source.
- **The sdist ships the prebuilt bundle**, so installing from source also needs no Node.
- **Dev experience:** running from a git checkout uses the Vite dev server proxying `/api` to
  FastAPI, with hot reload. `make web-build` produces the bundle locally.
- **If `dist/` is missing at runtime**, `serve` fails with an actionable message ("running from a
  git checkout: run `make web-build`") rather than serving a `404` on `/`.
- **CI verifies the property that actually matters:** install the built wheel into a clean,
  Node-free environment and confirm the SPA serves. This is the exact thing that breaks silently
  and is otherwise discovered by a user.
- **Zero network egress from the bundle.** Fonts, icons and Three.js are all bundled. No CDN, no
  Google Fonts, no analytics. A remote font is an egress, and this page is served by a process
  holding a read connection to a production database.

## Consequences

**Buys:** a typed, unit-tested, visually-regression-tested front end, and a Python install
experience with no JavaScript in it. The zero-egress property is verifiable and is part of the
security story.

**Costs:**
- Two toolchains in one repository, two lint configurations, two CI paths. Unavoidable for any
  Python package with a real web UI.
- The release pipeline depends on Node, so a Node-side break blocks a release. Mitigated by
  pinning versions and committing `package-lock.json`.
- Contributors need Node to work on the visualizer, though not to work on the Python.
- Bundle size must be actively watched. Budget: under 500 KB gzipped with Three.js tree-shaken,
  asserted in CI so a careless import cannot quietly triple it.

## Alternatives considered

- **No build step: vanilla ES modules with import maps, Three.js from a CDN.** Genuinely
  tempting for simplicity, and rejected for two reasons: the CDN violates the zero-egress rule
  outright, and no types means no test coverage of the buffer-decoding logic where the real risk
  lives.
- **Committing `dist/` to the repository.** Rejected: merge conflicts on minified bundles, and no
  way for a reviewer to confirm the artifact corresponds to the source.
- **Serving the UI from a separate npm package.** Rejected: two release cadences to keep in sync
  for one tool, and version-skew bugs that would be reported as visualization bugs.
- **React or Svelte.** Rejected: more build surface and bundle weight than the application code.
  Reconsider only if the UI grows several more views.
- **Building the front end at `pip install` time.** Rejected: requires Node on the user's
  machine, which is the constraint this whole decision exists to satisfy.

## Revisit if

- The UI grows enough that hand-written DOM becomes the bottleneck rather than the framework
  would be.
- Python packaging gains a first-class way to declare and build a front-end asset, making the
  Hatch build hook unnecessary.
