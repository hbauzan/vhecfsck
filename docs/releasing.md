# Release Engineering Guide

This document describes the process for packaging, testing, and publishing releases of `vhecfsck`.

---

## 1. Release Architecture & Security

`vhecfsck` uses standard Python packaging (`hatchling` backend declared in `pyproject.toml`) and automated GitHub Actions workflows.

* **Versioning Standard**: [Semantic Versioning 2.0.0](https://semver.org/). `0.1.0` establishes stable CLI parameters, report schemas, and exit codes.
* **Authentication**: PyPI releases use **Trusted Publishing via OpenID Connect (OIDC)** (`id-token: write`). No long-lived API tokens or secret keys are stored in the repository.
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

The `.github/workflows/release.yml` workflow runs automatically upon tag push:

1. **Build Step**: Checks out code, sets up Python 3.11/`uv`, and executes `uv build`.
2. **Clean Smoke Test**: Installs the newly built wheel in an isolated temporary environment and executes `vhecfsck demo`.
3. **PyPI Publishing**: Publishes wheel and sdist to PyPI via OIDC authentication.
4. **GitHub Release**: Creates a new GitHub Release with attached `.whl` and `.tar.gz` artifacts.

---

## 5. Post-Release Verification

Verify that the published package can be installed and executed globally without local repository dependencies:

```bash
uvx vhecfsck@0.1.0 demo
```
