---
name: unit-test-audit
description: Audit an existing unit-test suite for useless, redundant, misleading, brittle, or weak tests and produce an evidence-backed list of tests to remove, rewrite, or consolidate. Use when the user asks whether tests are valuable, requests a test-quality audit, or asks for an independent review of newly written tests. Do not use for ordinary test-failure debugging or when the primary request is to add coverage.
---

# Unit Test Audit

Act as a skeptical test-suite auditor. Review every unit test in scope, but
report only tests with a concrete usefulness or quality problem. Do not modify
tests or production code unless the user separately requests fixes.

## Establish Complete Scope

Read repository instructions, test configuration, CI commands, and test-folder
conventions before judging tests. Determine which tests are unit tests from
explicit markers, configured paths, naming, dependencies, and fixtures.

- Prefer the framework's collection command to inventory test node IDs without
  executing them.
- Exclude vendored dependencies, generated build artifacts, virtual
  environments, and tests explicitly classified as integration, end-to-end, or
  live-service tests.
- If the repository does not distinguish test types, audit all tests that can
  run without external services and state that working definition.
- Count collected cases and reviewed test definitions separately. For a
  parametrized test, evaluate the shared definition and identify individual
  parameter rows only when their value differs.
- If collection is incomplete or unsafe, use a static inventory and disclose
  exactly what could not be reviewed. Never claim a complete audit without a
  reconciled inventory.

## Gather Evidence Safely

Inspect the relevant production behavior, fixtures, fakes, helpers, and nearby
tests before classifying a test. Run the safest repository-defined unit-test
command when it does not access live services or mutate external state. Do not
run live, destructive, or credential-dependent tests without authorization.

Passing status and coverage are supporting signals, not proof of usefulness.
Do not install new analysis or mutation-testing dependencies merely for the
audit. If existing coverage data or tooling is available, use it only to help
trace execution.

When this repository provides `scripts/check_test_quality.py`, run it as an
initial mechanical screen. Treat a clean result as evidence only that the
listed static anti-patterns are absent, not that the tests are valuable.

For every test definition, determine:

1. The contract, invariant, branch, regression, or failure mode it intends to
   protect.
2. Which production behavior could make it fail.
3. Whether its assertions observe that behavior rather than only its setup or
   mocks.
4. Whether another test already protects the same behavior with equal or
   stronger failure sensitivity.
5. Whether the test is deterministic and coupled only to details that matter
   to the contract.

Give extra scrutiny to these failure-prone patterns:

- An expected value copied from current implementation behavior without being
  reconciled with the domain contract.
- An import-isolation test that runs in the already-imported interpreter.
- A fake that retains only its most recent call when several calls matter.
- A privacy test that checks a generic substring instead of a unique sentinel
  across the entire outward representation.
- A catalog test that selects an entry by numeric position when order is not
  the contract.

For an important new or rewritten test, use
`scripts/run_test_challenge.py` when available to test one plausible mutation
in an isolated repository copy. Choose a syntactically valid behavior change,
run only the relevant test node IDs, and confirm the unmodified baseline passes
before accepting a mutation-caused failure. A killed mutation supports failure
sensitivity; it does not prove that the test's expected value is correct.

## Classification Rubric

Flag a test only when the evidence supports at least one of these verdicts:

- **Useless — remove:** It has no meaningful assertion, cannot fail because of
  a relevant production regression, only proves the test setup or framework,
  never reaches the claimed code path, or is permanently dead without a
  documented purpose.
- **Redundant — consolidate:** Another test exercises the same path, inputs,
  observable behavior, and failure mode with equal or stronger assertions.
  Similar-looking tests are not redundant when they protect distinct boundary
  values, errors, permissions, formats, or regression histories.
- **Weak — rewrite:** It targets a meaningful behavior but its oracle is too
  shallow, broad, or indirect to catch plausible regressions.
- **Misleading — rewrite or remove:** Its name or comments claim behavior that
  its setup and assertions do not exercise, or it passes for a reason unrelated
  to the claimed contract.
- **Brittle — rewrite:** It primarily asserts incidental implementation detail,
  unstable ordering, timing, formatting, or mock choreography without
  protecting a required contract.

Do not automatically flag a test because it is short, has one assertion, uses
mocks, checks a getter, is a snapshot, overlaps another test, or covers a simple
branch. Judge whether it can catch a meaningful regression in this repository.

Treat skipped and expected-failure tests carefully. Flag them only when the
reason is stale, the condition can no longer change, or the test no longer
protects a supported behavior. Preserve tests that document an active bug,
compatibility boundary, or safety invariant.

## Calibrate Recommendations

Recommend the smallest action that retains useful coverage:

- `remove` only when no meaningful protection would be lost;
- `consolidate` when one stronger test can retain all distinct assertions;
- `rewrite` when the behavior matters but the setup or oracle is defective;
- `investigate` when evidence suggests a problem but intent or production
  behavior is genuinely unclear.

For `remove` and `consolidate`, name the existing test that preserves the
coverage. For `rewrite`, state the observable behavior the replacement should
assert. Never recommend deletion solely to reduce test count or runtime.

## Report

Lead with the audit result and completeness evidence. Include:

1. **Scope:** test roots, framework, exclusions, collection method, collected
   cases, reviewed definitions, and whether the baseline suite passed.
2. **Flagged tests:** an impact-ordered table containing:
   - clickable `path:line` and exact test name;
   - verdict and recommended action;
   - the behavior the test appears to target;
   - concrete evidence of why it fails to protect that behavior;
   - retained or replacement coverage;
   - confidence: high, medium, or low.
3. **Suite-level patterns:** only recurring causes that explain multiple
   findings, such as a helper that makes assertions tautological.
4. **Limitations:** tests or production paths that could not be inspected or
   safely executed.

Do not bury the requested list inside general testing advice. Do not list good
tests individually unless one is needed as evidence that a flagged test is
redundant. If no tests meet the threshold, say so plainly and report the scope
and residual uncertainty rather than inventing findings.

## Final Check

Before returning the audit, confirm that:

- Every collected unit-test definition was reviewed or explicitly accounted
  for.
- Every finding cites the exact test and relevant production or overlapping
  test evidence.
- “Redundant” findings compare observable behavior and failure modes, not only
  names or code similarity.
- Recommendations preserve important regression, boundary, error, security,
  and compatibility coverage.
- Commands and results are reported accurately, and no live external call was
  made without authorization.
