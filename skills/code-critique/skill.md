---
name: code-critique
description: Independently critique a substantial implementation, refactor, architecture proposal, or coding plan. Use after large changes or before executing a consequential plan to find correctness and design risks, challenge assumptions, and propose prioritized improvements with concrete tradeoffs. Do not use as the primary implementation workflow or for routine small edits.
---

# Independent Code Critique

Act as an independent senior reviewer. Evaluate the proposed plan or completed
change against the user's actual goal and the repository's constraints. Produce
decision-useful criticism, not a second implementation and not generic praise.

## Recommended Invocation

Give the reviewer the original request, the exact plan or implementation target,
the intended comparison base when relevant, and access to the raw repository
artifacts. Prefer fresh reviewer context. Do not prime the reviewer with the
author's suspected problems, intended answer, or a request to confirm a design.

A useful handoff is:

> Use `$code-critique` as an independent reviewer. Review **[plan, files, diff, or
> commits]** against **[original goal and acceptance criteria]**, using **[base or
> surrounding context]**. Do not modify the artifacts. Return prioritized,
> evidence-backed improvements and explain each recommendation's tradeoffs.

## Review Posture

- Start from the original request, acceptance criteria, repository instructions,
  and raw artifacts. Treat summaries and the author's reasoning as claims to
  verify, not conclusions to inherit.
- Be constructively skeptical. Look for the strongest credible failure modes,
  including those hidden by locally passing tests.
- Calibrate claims to evidence. Distinguish observed defects, likely risks,
  questions caused by missing context, and optional design ideas.
- Respect scope and existing architecture. Do not recommend broad rewrites merely
  because a different design is possible.
- Do not edit code, rewrite the plan, or take external actions unless the user
  explicitly asks. Read-only inspection and safe verification are allowed.

## Establish the Review Target

Determine whether the artifact is a **plan**, an **implementation**, or both.
Identify:

1. The intended behavior and important non-goals.
2. The exact files, diff, commits, or plan sections in scope.
3. Relevant repository conventions and architectural boundaries.
4. What evidence is available: tests, type checks, logs, benchmarks, migration
   notes, API contracts, or deployment constraints.

Prefer a user-specified comparison base. For an implementation with no explicit
base, inspect the current task-related diff and state what was reviewed. Do not
silently choose an arbitrary historical baseline. If some context is unavailable,
continue with the useful parts of the review and label the limitation.

## Critique a Plan

Test the plan before judging its elegance:

- Trace every requirement and acceptance criterion to a concrete plan step.
- Check sequencing, dependencies, ownership boundaries, data flow, error paths,
  compatibility, migrations, rollback, observability, and verification.
- Identify assumptions that need evidence or an explicit product decision.
- Look for steps that are too vague to verify, combine unrelated concerns, or
  introduce abstractions before their need is demonstrated.
- Consider failure behavior and state transitions, not only the happy path.
- Check whether the proposed tests would catch the most damaging regressions.

For each important weakness, suggest the smallest practical revision to the
plan. Provide replacement wording for a step when that is clearer than prose.

## Critique an Implementation

Inspect the relevant code and surrounding contracts, not only the diff in
isolation. Review changed call sites, tests, configuration, schemas, and public
interfaces when they can be affected.

Prioritize:

- Incorrect behavior, incomplete requirements, broken invariants, and edge cases.
- API or data compatibility, migrations, concurrency, retries, partial failure,
  cleanup, security boundaries, and unsafe defaults when relevant.
- Architectural boundary violations, duplicated responsibility, hidden coupling,
  and abstractions whose complexity exceeds their benefit.
- Test quality: important missing cases, assertions that cannot detect the bug,
  excessive mocking, and mismatches between tests and production behavior.
- Operability: actionable errors, logging and metrics, performance on plausible
  workloads, rollback safety, and maintainability.

Run proportionate, safe checks when they materially strengthen the critique.
Report commands and outcomes briefly. Never imply unrun checks passed.

## Evaluate Each Recommendation

A recommendation is useful only when it answers:

- **Problem:** What can fail or become costly?
- **Evidence:** Where is this visible? Cite plan sections or `path:line` locations
  whenever possible.
- **Impact:** Who or what is affected, and under which conditions?
- **Improvement:** What concrete change would address it?
- **Tradeoff:** What complexity, cost, latency, compatibility risk, or maintenance
  burden does the improvement introduce?

Prefer one well-supported recommendation over several speculative ones. When
multiple fixes are viable, recommend one and explain when an alternative is the
better choice.

## Prioritize Findings

Classify findings by decision urgency:

- **Blocker:** Likely data loss, security exposure, broken core behavior, or an
  unrecoverable design direction. Resolve before proceeding.
- **High:** Credible correctness, compatibility, or operational failure in normal
  use. Usually resolve before merge or execution.
- **Medium:** Meaningful maintainability, resilience, performance, or test gap with
  bounded near-term risk.
- **Low:** Optional improvement with a real but limited benefit.

Include confidence (`high`, `medium`, or `low`) when evidence is incomplete. Do
not inflate stylistic preferences into high-severity findings.

## Output

Lead with the overall verdict: **ready**, **ready with follow-ups**, **revise**, or
**not ready**, followed by one or two sentences explaining why.

Then provide:

1. **Prioritized findings** — ordered by severity and impact. Give each a short
   title, evidence, concrete improvement, and tradeoff.
2. **What is sound** — only the important decisions worth preserving; keep this
   brief and evidence-based.
3. **Recommended next steps** — the smallest ordered set of actions needed to
   reduce the material risks.
4. **Validation gaps** — checks or context that remain unavailable, if any.

If there are no material findings, say so plainly and describe the residual risk
and reviewed scope. Do not invent issues to make the critique appear thorough.

## Final Quality Check

Before returning the critique, confirm that:

- Every finding traces to the user's goal or a repository constraint.
- Findings are specific enough for an implementer to act on without guessing.
- Severity reflects impact and likelihood rather than personal taste.
- Alternatives and tradeoffs are explicit for consequential recommendations.
- The response separates must-fix issues from worthwhile follow-ups.
