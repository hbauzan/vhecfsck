# STRUCTURED BUG DIAGNOSIS PROTOCOL

When a bug is reported or tests are failing, follow this 6-phase debugging loop. Do not skip phases unless explicitly justified.

> **[lessons-learned.md](./lessons-learned.md) belongs to this loop — at Phase 3, not before it.** It is the project's handoff memory: what previous agents learned, including the invariants that have already been broken once. A large share of bugs are one of those breaking again, and the file turns such a bug from a fresh investigation into a top-ranked hypothesis that arrives with evidence and a known fix. Read it when you start generating hypotheses, not while building the repro — Phase 1 forbids theorising before a red-capable command exists, and reading a catalogue of causes is theorising. Writing to it is a handoff activity, not a task-closing one; see its §5.

---

## Phase 1: Build a Feedback Loop
Everything else is mechanical. If you have a tight, pass/fail signal that goes red on *this specific bug*, you will find the cause. If not, staring at code will not save you.

### 1.1. Constructing the Loop (Try in order)
1. **Failing test** at whatever seam reaches the bug (unit, integration, e2e).
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer) asserting on DOM/console.
5. **Replay a captured trace**: save a network request/payload and run in isolation.
6. **Throwaway harness**: spin up a minimal subset of the system (one service, mocked dependencies).
7. **Property / fuzz loop**: run 1000 random inputs to trigger a flake.
8. **Bisection harness**: automate checking versions to `git bisect run`.
9. **Differential loop**: run same input through old vs new versions and diff.
10. **HITL bash script**: drive human-in-the-loop steps via a structured script.

### 1.2. Tighten and Verify
- **Tighten the loop**: Make it fast (seconds, not minutes), deterministic (pin time/RNG, isolate network), and sharp (assert on the symptom, not just "didn't crash").
- **LLM determinism**: When the bug is in a model-touching path, remove the model as a variable first. Mock/stub the provider interface or replay a recorded response; if a live model is unavoidable, pin `temperature=0` and a fixed seed. A loop whose redness depends on sampling noise is not red-capable. See [SKILL.md](./SKILL.md) §3.2.
- **Phase 1 Completion Criterion**: You must establish **one command** that runs unattended, is fast, deterministic, and **red-capable** (successfully triggers and catches this exact bug).
- **Prohibited action**: Do not jump to hypotheses or read code to build a theory before this command exists. No red-capable command, no Phase 2.

---

## Phase 2: Reproduce + Minimise
Run the feedback loop and watch it go red.
1. Confirm the loop produces the **user's exact described symptom** (not a different nearby issue).
2. Shrink the repro to the **smallest scenario that still goes red**. Cut inputs, configuration, and steps one at a time.
3. Done when every remaining element is load-bearing (removing any one element makes the loop go green).

---

## Phase 3: Hypothesise
1. **Read [lessons-learned.md](./lessons-learned.md) first.** Check the minimised repro from Phase 2 against the recorded invariants. If one of them covers this area, it is a hypothesis that already comes with evidence and a known fix — rank it at the top and test it first. This is the cheapest hypothesis available and skipping it is how the same bug gets solved twice.
2. Generate **3–5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors on the first plausible idea.
3. Ensure each hypothesis is **falsifiable**: state the prediction it makes.
   > **Format**: *"If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."*
4. **Show the ranked list to the user** before testing. If the user is AFK, proceed with testing the top hypothesis.

---

## Phase 4: Instrument
1. Map each probe to a specific prediction from Phase 3. Change **one variable at a time**.
2. **Tag every debug log** with a unique prefix (e.g., `[DEBUG-a4f2]`) so they can be cleaned up in a single grep.
3. For performance regressions, establish baseline measurements (`performance.now()`, query plans) before making modifications.

---

## Phase 5: Fix + Regression Test
1. Write a regression test **before the fix** (only if a correct seam exists).
2. If no correct seam exists (e.g. tests cannot replicate the integration path), note this finding. Codebase architecture is preventing the bug from being locked down.
3. Steps: Turn minimised repro into a failing test -> Watch it fail -> Apply fix -> Watch it pass -> Re-run the Phase 1 loop against the original un-minimised repro.

---

## Phase 6: Cleanup + Post-Mortem
Before declaring a bug resolved, complete this checklist:
- [ ] Original repro no longer reproduces (re-run Phase 1 loop).
- [ ] Regression test passes (or absence of seam is documented).
- [ ] All tagged `[DEBUG-...]` instrumentation logs are removed.
- [ ] Throwaway prototypes/harnesses are deleted.
- [ ] `make verify` green — the whole gate, not just the test you were staring at ([guardrails.md](./guardrails.md) §1).
- [ ] Correct hypothesis is documented in the commit/PR message.
- [ ] **Post-Mortem**: Ask: *What would have prevented this bug?* If it requires architectural improvements (better test seams, less coupling), log a task or report it to the user. If the answer is a **static guard**, that is the highest-value outcome available — see [guardrails.md](./guardrails.md) §5.
- [ ] **If the cause was already written in [lessons-learned.md](./lessons-learned.md)**, say so explicitly in the report. A recorded lesson that failed to prevent a recurrence is not a documentation problem — prose does not enforce anything. That invariant has earned a static guard or a regression test ([guardrails.md](./guardrails.md) §5).
- [ ] If the root cause is a **new** durable invariant, **propose it in the report** so it can go into the next handoff. Do not append it to [lessons-learned.md](./lessons-learned.md) yourself unless the user asks — see its §5.2.
