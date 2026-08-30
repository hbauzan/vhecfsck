# CODEBASE DESIGN AND IMPLEMENTATION PRINCIPLES

All codebase changes should follow the deep module design principles and a vertical, test-driven implementation workflow.

---

## 1. DEEP MODULE DESIGN

Aim to design **deep modules**: modules that put a lot of behavior behind a small interface, placed at a clean seam, testable through that interface.

### 1.1. Glossary of Terms
Do not substitute generic terms (like "component," "service," "API," or "boundary") for these design elements:
- **Module**: Anything with an interface and an implementation (function, class, package, or tier-spanning slice).
- **Interface**: Everything a caller must know to use the module correctly (types, invariants, ordering constraints, error modes, configuration, and performance characteristics).
- **Implementation**: What is inside the module (its body of code).
- **Adapter**: A concrete object/code that satisfies an interface at a seam. Describes the *role*, not substance.
- **Depth**: Leverage at the interface. A module is **deep** when a large amount of behavior sits behind a small interface. It is **shallow** when the interface is as complex as the implementation (avoid shallow modules).
- **Seam**: A place where you can alter behavior without editing in that place (the location of a module's interface).
- **Leverage**: Capability per unit of interface learned (one implementation pays back across N call sites).
- **Locality**: Concentration of change, bugs, and knowledge in one place rather than spreading across callers.

### 1.2. Design Principles
- **Depth is a property of the interface, not the implementation**: A deep module can be internally composed of small, mockable, swappable parts, as long as they remain private to its implementation.
- **The Deletion Test**: If you delete the module and the complexity vanishes, it was a pass-through (shallow). If the complexity reappears across N callers, it was earning its keep (deep).
- **The interface is the test surface**: Callers and tests cross the same seam. If you need to test past the interface, the module is probably the wrong shape.
- **One adapter = hypothetical seam; Two adapters = real seam**: Don't introduce interfaces or seams unless something actually varies across them.
  - *Canonical LLM example*: a **local** model backend and a **remote** API are two adapters behind one provider interface — that is a real seam, so the abstraction earns its keep. A single provider with no alternative does not (yet) justify one. See [SKILL.md](./SKILL.md) §3.2.
- **Design for Testability**:
  1. *Accept dependencies, don't create them* (pass collaborators in).
  2. *Return results, don't produce side effects* where possible (pure computations).
  3. *Small surface area* (fewer methods/parameters = simpler setup and fewer tests).

---

## 2. IMPLEMENTATION WORKFLOW: VERTICAL SLICES

### 2.1. Tracer Bullets vs Horizontal Slicing (Anti-Pattern)
- **Anti-Pattern (Horizontal Slicing)**: Writing all tests first, then writing all implementation code, or implementing layer-by-layer (e.g. database first, then api, then frontend). This leads to tests that check imagined shapes rather than actual behavior.
- **Correct Approach (Vertical Slicing)**: Implement features via **tracer bullets**. Each issue or step is a thin vertical slice cutting through all integration layers (schema, API, UI, tests) end-to-end. One slice should be demoable and verifiable.

```
WRONG (Horizontal):
  RED:   test1, test2, test3, test4
  GREEN: impl1, impl2, impl3, impl4

RIGHT (Vertical):
  RED→GREEN: test1 → impl1
  RED→GREEN: test2 → impl2
```

---

## 3. TEST-DRIVEN DEVELOPMENT (TDD)

Tests must verify behavior through public interfaces, not implementation details.

### 3.1. The TDD Cycle
1. **Planning**:
   - Confirm interface changes and behavior priorities with the user.
   - List the behaviors to test (not implementation steps).
2. **Tracer Bullet**:
   - Write ONE test for the first behavior -> Watch it fail (**RED**).
   - Write the minimal code to pass -> Watch it pass (**GREEN**).
3. **Incremental Loop**:
   - For each remaining behavior, repeat: Write next test (RED) -> Minimal code to pass (GREEN). Do not anticipate future tests or write speculative features.
4. **Refactor**:
   - Extract duplication, deepen modules, and apply SOLID principles.
   - **Never refactor while RED**. Get to GREEN first, then refactor, running tests after each step.

---

## 4. ERROR TAXONOMY AND EXIT CODES

"Structured error handling" ([SKILL.md](./SKILL.md) §3.1) means this specific thing. Define it
once, centrally, **before** any code can raise something ad hoc — a taxonomy retrofitted after
fifty raise sites is a rewrite, not a refactor.

### 4.1. The error type
One base class, subclassed per failure mode, each carrying three things:
- `exit_code` — the process-level answer (§4.2).
- `code` — a stable, machine-readable string (`provider.timeout`). Callers and log parsers key
  off this, so it survives rewording; the human message does not.
- `hint` — one sentence telling the user what to do next.

### 4.2. The exit-code table
Anything that runs in CI, in a pipeline, or under another agent is read by a program before it
is read by a person. `sys.exit(1)` for everything makes "the model refused" indistinguishable
from "you passed a bad flag".

| Code | Name | Means |
| :--- | :--- | :--- |
| `0` | `OK` | Succeeded. Diagnostic notes, if any, go to **stderr** — do not spend exit `1` on "ok with an asterisk". POSIX and CI treat `1` as failure. |
| `2` | `FAIL` | Ran correctly and the answer is negative — checks failed, output rejected. |
| `3` | `INCONCLUSIVE` | Could not determine an answer. A required capability was missing, a provider was unreachable, a limit was hit. **Not** the same as failure. |
| `4` | `USAGE` | The caller is wrong: bad flag, bad config key, unparseable input. |
| `8` | `WARN` | Completed, but something the caller should see. `≥ 8` so shells and CI do not confuse it with a generic failure. Prefer `0` + stderr when the caller should keep going. |
| `70` | `INTERNAL` | A bug in this program. (`EX_SOFTWARE`, `sysexits.h`.) |

A product ADR may lock a different table (for example an already-shipped CLI that uses
`1` = `WARN`). Do not "fix" that contract to match this template.

`3` is the one people skip, and it is the one that matters most in LLM work. A timeout against
a remote provider is not a failed check; reporting it as `2` makes a flaky endpoint look like a
broken build.

### 4.3. Rules
- **One top-level handler** maps any uncaught exception to `70`, prints a short message, and
  points at `--debug` for the traceback. Users never see a raw traceback by default; the person
  filing the bug report always can.
- **Never invent a value you could not compute.** Returning `0`, `""` or a plausible default
  where the real answer is unknown is the most damaging class of bug in this stack, because it
  looks like a healthy result. Raise the `INCONCLUSIVE` error, or return an explicit "unknown"
  state that the caller has to handle.
- **Never `raise Exception` or `SystemExit`** outside the error module. Enforceable as a lint
  rule; do enforce it.
- **Test the mapping from a table**, so adding an error type without an exit code fails the
  suite rather than silently defaulting.
