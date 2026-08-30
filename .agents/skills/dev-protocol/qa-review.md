# QUALITY ASSURANCE & SYSTEM REVIEW WORKFLOWS

Follow these protocols to maintain spec compliance, code quality, and clear, durable issue reporting.

---

## 1. QUALITY ASSURANCE & ISSUE FILING

When the user describes problems during QA, or when planning a feature, translate them into durable, clear issues on the project issue tracker.

### 1.1. Rules for Filing Issues
- **Durable**: Issues should remain valid after major refactors.
- **Describe behaviors, not code**: Say *"the login page fails to redirect after submitting"* instead of *"authController.js throws on line 42"*.
- **No file paths or line numbers**: These go stale rapidly.
- **Use the project's domain language**: Reference terms as defined in `architecture_spec.md`, or the repo's equivalent (`roadmap/glossary.md`, ADRs). Do not create `architecture_spec.md` by reflex.
- **Reproduction steps are mandatory**: List concrete, numbered steps a developer can follow, including inputs, flags, or configuration.

### 1.2. Single Issue vs Breakdown
- **Single Issue**: Use when it is a single behavior wrong in one place, or multiple symptoms caused by the exact same root behavior.
- **Breakdown**: Break a task or report into multiple issues when:
  - The work spans multiple independent areas.
  - Slices are independently fixable and verifiable.
  - There are blocker/dependency relationships (e.g. Issue B cannot be tested until Issue A is completed).
- **Tracer Bullet Breakdown**: When breaking down a plan, create **vertical slices** (tracer bullets) that cut through all layers (schema -> API -> UI -> tests) and are demoable. Publish issues in dependency order (blockers first).

---

## 2. TWO-AXIS REVIEW WORKFLOW

**Precondition: `make verify` is green** ([guardrails.md](./guardrails.md) §1). Reviewing a diff that does not lint, type-check or pass its tests burns two sub-agents rediscovering what one command already knew. The gate answers "is it correct?"; the review answers "is it the right thing, built the right way?".

To verify changes before merging, perform a review of the diff against `HEAD` along two distinct, independent axes:

### 2.1. The Two Review Axes
1. **Standards Axis**: Checks if the diff conforms to this repository's documented coding standards — `CODING_STANDARDS.md` **or** the repo's ruff / typechecker / ADR set. Do not invent `CODING_STANDARDS.md` if those already are the standard.
2. **Spec Axis**: Checks if the diff faithfully implements the originating issue, spec, or PRD.
   - Detects missing/partial requirements.
   - Detects scope creep (behavior in the diff that wasn't asked for).
   - Detects incorrect implementations of requirements.

### 2.2. Parallel Evaluation Protocol
- **Parallel Sub-Agents**: Run the Standards review and Spec review as two parallel sub-agents (using `general-purpose` sub-agents) to prevent context pollution.
- **Integration**: Aggregate both reports under `## Standards` and `## Spec` headers verbatim. Do not merge or rerank their findings, as a change can pass one axis while failing the other (e.g., standard-compliant code that implements the wrong feature).
