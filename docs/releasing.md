# Release Engineering Guide

This document describes the process for packaging, testing, and publishing releases of `vhecfsck`.

---

## 1. Release Architecture & Security

`vhecfsck` uses standard Python packaging (`hatchling` backend declared in `pyproject.toml`) and automated GitHub Actions workflows.

* **Versioning Standard**: [Semantic Versioning 2.0.0](https://semver.org/). `0.1.0` establishes stable CLI parameters, report schemas, and exit codes.
* **Authentication**: no long-lived API tokens or secret keys are stored in the repository, and none ever should be. Releases go through **Trusted Publishing via OpenID Connect (OIDC)** (`id-token: write`, no `password` input). The `verify-and-build` job uses the GitHub environment `pypi`, so a tag cannot publish without owner approval. If that path is unavailable, use the manual fallback in §6.
* **Artifact Integrity**: The build pipeline compiles both source distribution (`.tar.gz`) and binary wheel (`.whl`), embedding the static visualization bundle processed by `hatch_build.py`.

---

## 2. Pre-Release Checklist

Before tagging a release, complete the following verification steps on `main`:

1. **Clean Quality Gate**:
   ```bash
   make verify
   ```
2. **Comprehensive Verification**:
   ```bash
   make verify-full
   ```
3. **Verify Local Wheel Build & Smoke Test**:
   ```bash
   uv build
   uvx --from dist/*.whl vhecfsck demo
   ```
4. **Update `CHANGELOG.md`**:
   Ensure all changes under `[Unreleased]` are moved to `[0.1.0] - YYYY-MM-DD`.

---

## 3. Tagging and Publishing

Trigger the automated release workflow by creating and pushing a signed git tag:

```bash
# 1. Create tag
git tag -a v0.1.0 -m "v0.1.0 release"

# 2. Push tag to GitHub
git push origin v0.1.0
```

---

## 4. Automated Workflow Execution

The `.github/workflows/release.yml` workflow runs automatically upon tag push.
The job is bound to the GitHub environment `pypi` and **waits for owner approval**
before any step (including build) runs.

1. **Build Step**: Checks out code, sets up Python 3.11/`uv`, and executes `uv build`.
2. **Clean Smoke Test**: Installs the newly built wheel in an isolated temporary environment and executes `vhecfsck demo`. The default demo is tombstoned **FAIL** (exit 2); the job treats exits 0–3 as a runnable wheel and fails on usage (4) or internal (70).
3. **PyPI Publishing**: Publishes wheel and sdist to PyPI via OIDC authentication.
4. **GitHub Release**: Creates a new GitHub Release with attached `.whl` and `.tar.gz` artifacts.

---

## 5. Post-Release Verification

Verify that the published package can be installed and executed globally without local repository dependencies:

```bash
uvx vhecfsck@0.1.0 demo
```

---

## 6. Manual Release Procedure (fallback)

Use this only if the automated path in §3 is unavailable. Every step matters; two of them
have silently produced a bad artefact before.

1. **Bump the version in two places, not one.** `pyproject.toml`, and the
   `tool_version` field embedded in all four golden fixtures under
   `tests/fixtures/golden/`. The golden comparison is byte-exact, so a bump without
   the fixtures turns four tests red — this happened at `0.1.1` and again at `0.1.2`.

2. **Move `[Unreleased]` to a dated section** in `CHANGELOG.md`.

3. **Rebuild the front-end bundle.**

   ```bash
   make web-build
   ```

   `hatch_build.py` returns early when `vhecfsck/web/dist/index.html` exists and does
   **not** check whether it is older than the sources. Skipping this ships whatever
   bundle happens to be on disk, silently.

4. **Empty `dist/` before building.**

   ```bash
   rm -rf dist/*
   ```

   `uv publish` uploads `dist/*` by default. Leftover wheels from earlier versions
   will be picked up.

5. **Gate, build, smoke test.**

   ```bash
   make verify
   uv build
   uvx --from dist/*.whl vhecfsck demo
   ```

6. **Upload, then tag.**

   ```bash
   uv publish --token pypi-...
   git tag -a v0.1.3 -m "v0.1.3"
   git push origin main --tags
   ```

   Upload first: a tag pointing at a version that failed to publish is worse than no
   tag. PyPI refuses re-uploads of an existing version, so a failed publish cannot be
   retried under the same number.

7. **Verify from a clean environment**, per §5.

> **On PyPI landing-page updates.** PyPI freezes the long description into the
> uploaded artefact. Pushing to GitHub does not change the project page — only
> publishing a new release does. If a README or CHANGELOG fix needs to appear on
> pypi.org, it needs a version.
