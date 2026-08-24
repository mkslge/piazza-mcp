---
name: change-walkthrough
description: Explain substantial completed code changes as a guided technical walkthrough with Mermaid diagrams and an efficient, dependency-aware review order. Use after implementing a feature, bug fix, or refactor, or when the user asks what changed, how the new flow works, or which generated code to review first. Do not use for the primary implementation or as a substitute for an independent code critique.
---

# Change Walkthrough

Teach the change as a coherent system, then guide the user through reviewing the
actual code in the order that builds understanding fastest. Explain intent,
relationships, and design decisions rather than narrating the diff line by line.

## Ground the Explanation

Before explaining, inspect the original request, repository instructions, plan or
acceptance criteria, and the complete change in scope. Read enough surrounding
code to understand existing contracts and call paths.

- Prefer a user-specified diff or comparison base. Otherwise state exactly which
  working-tree changes, commits, or files were reviewed.
- Include relevant untracked files; a diff alone may omit them.
- Separate behavior-changing code from tests, configuration, generated files,
  formatting, and incidental edits.
- Verify claims against the final code. Do not describe an abandoned plan as if
  it were implemented.
- Do not modify code while producing the walkthrough unless the user separately
  asks for changes.

If the scope or baseline remains uncertain, explain the useful verified portion
and label the limitation instead of silently guessing.

## Build the Mental Model First

Begin with the user's goal and the resulting behavior. In a few sentences,
explain:

1. What was possible before.
2. What is possible now.
3. Where the main responsibility lives.
4. Which important behavior intentionally did not change.

Use a compact before-and-after table when it clarifies a changed contract,
responsibility, data shape, or control flow. Avoid listing every file here; the
ordered review tour handles implementation detail.

## Show the Flow with Mermaid

For every non-trivial walkthrough, include at least one Mermaid diagram that
captures the most important verified relationship. Choose the diagram from the
system's actual shape:

- `flowchart` for control flow, data movement, dependencies, or component
  boundaries.
- `sequenceDiagram` for interactions whose ordering, request/response behavior,
  or failure propagation matters.
- `stateDiagram-v2` for lifecycles, retries, status changes, or other stateful
  behavior.

Prefer one useful diagram over several redundant ones. Add a second diagram only
when it explains a materially different view, such as architecture versus a
single request's runtime sequence.

Diagram rules:

- Represent only behavior confirmed in the code.
- Include the meaningful entrypoint, transformations, boundaries, outputs, and
  important failure or fallback path when relevant.
- Mark new or changed components in their labels, such as `Parser (changed)`;
  do not rely on color alone.
- Keep the primary diagram small enough to scan, normally fewer than 12 nodes or
  participants. Collapse incidental helpers into the owning component.
- Keep labels short and define unfamiliar terms in the surrounding prose.
- Use stable Mermaid syntax and simple alphanumeric node identifiers. Explain
  dashed edges or other notation when their meaning is not obvious.

For a genuinely small change with no meaningful multi-step flow, use a minimal
dependency diagram or explicitly say why a larger diagram would be misleading.

## Choose the Ideal Code Review Order

Do not default to alphabetical file order, diff order, or implementation order.
Build a review path that minimizes how much unexplained context the user must
hold at once.

Choose the starting point based on the change:

- **Feature or API change:** public contract or high-signal acceptance test,
  then data shapes, core behavior, external boundaries, wiring, and proof tests.
- **Bug fix:** regression test or reproducible failure, then the defective logic,
  affected callers and invariants, and finally the broader test coverage.
- **Refactor:** preserved contract, new abstraction, migrated call sites, removed
  path, and equivalence tests.
- **Data pipeline:** input model, normalization or transformation stages,
  persistence or output adapter, orchestration, then edge-case tests.

Within that shape, prefer this dependency-aware progression when applicable:

1. **Goal and contract** — the requirement, public interface, schema, or test that
   states the behavior.
2. **Vocabulary and data shapes** — models, types, configuration, and invariants
   needed to read later logic.
3. **Core behavior** — the smallest unit that performs the main decision or
   transformation.
4. **Boundaries** — databases, files, networks, frameworks, and error translation.
5. **Composition and entrypoints** — how the pieces are constructed and invoked.
6. **Verification** — tests proving the happy path, edge cases, and regressions.
7. **Incidental artifacts** — generated files, lockfiles, documentation, and
   mechanical updates that are safe to skim last.

Adapt rather than forcing every change through all seven stages.

## Make Every Review Stop Actionable

Present the review tour as an ordered table or numbered list. Each stop must give:

- A clickable file and line or symbol reference when the interface supports it.
- Why this is the right point to read it.
- What changed at this location and why.
- The invariant, decision, or question the reviewer should verify.
- A depth cue: **deep review**, **normal review**, or **skim**.

Group files only when they form one concept. Place generated files and dependency
lockfiles last unless they are the substance of the change. If a file contains
unrelated user edits, identify the relevant symbols rather than claiming the
entire file belongs to the task.

After each major conceptual group, give a short checkpoint such as “At this point
you should be able to explain how an input becomes a validated domain object.”
These checkpoints let the user notice a missing mental link before moving on.

## Walk Through One Concrete Scenario

Trace one representative input or request through the diagram and review path.
Name the important values or state transitions at each step. Prefer a realistic
happy path, then briefly contrast the most consequential failure or edge case.

Do not invent payloads, outputs, performance characteristics, or error behavior.
If the repository does not contain a concrete example, clearly label a simplified
illustration and keep it consistent with verified types and contracts.

## Explain Decisions and Tradeoffs

Call out only decisions that materially affect correctness, extensibility,
compatibility, performance, operations, or maintenance. For each one, explain:

- The problem or constraint that shaped the choice.
- The selected approach and where it appears in the code.
- Its benefit and cost.
- The most credible alternative and when that alternative would be preferable.

Do not fabricate rejected alternatives or attribute intent that is not supported
by the request, code, or conversation. Label reasonable inference as inference.

## Report Verification and Residual Risk

End with a concise evidence table containing the checks actually run, their
result, and what each check establishes. Never imply that an unrun check passed.

Also identify:

- Important behavior that remains unverified.
- Compatibility, migration, rollback, security, or operational considerations
  that deserve attention.
- Deliberate limitations and follow-up work.
- Unrelated working-tree changes excluded from the walkthrough.

Distinguish a known problem from residual risk. This skill explains the change;
use an independent critique workflow when the user wants a skeptical design or
correctness review.

## Output Shape

Use the smallest structure that remains useful, generally in this order:

1. **Outcome and scope**
2. **Before and after**
3. **Mermaid flow**
4. **Guided code review order**
5. **Concrete scenario**
6. **Key decisions and tradeoffs**
7. **Verification and residual risk**

Skip empty sections. Keep basic syntax explanations brief, but define domain
concepts and non-obvious invariants. Do not paste large code blocks or restate the
entire diff; link to the implementation and quote only the few lines needed to
anchor an explanation.

## Final Quality Check

Before returning the walkthrough, confirm that:

- The Mermaid diagram matches the final implementation.
- Following the review order never requires a concept that has not yet been
  introduced.
- Every review stop tells the user what to verify, not merely what changed.
- Claims, links, test results, and line references are current and precise.
- The explanation separates implemented behavior, inferred rationale, and future
  suggestions.
- The user can explain the end-to-end flow after completing the tour.
