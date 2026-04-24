# AGENTS

## Scope

This file defines repository-specific working instructions for `astichi`.

## Agent requests: review vs edit

- When the user asks to review, verify, analyze, assess, report, or check,
  respond with read-only analysis only.
- Do not change files or implement fixes unless the user explicitly asks for
  edits, fixes, implementation, or an update.
- If analysis surfaces a problem, describe it and wait for direction rather
  than patching the tree unprompted.

## Start here

- **Read `dev-docs/AstichiSingleSourceSummary.md` first.** It is the active
  handoff and the authoritative project document.
- Then `dev-docs/AstichiCodingRules.md` for repository-specific coding rules.

## Authoritative docs

For active Astichi work, use these docs:

- `dev-docs/AstichiCodingRules.md`
- `dev-docs/AstichiSingleSourceSummary.md`

Archived docs under `dev-docs/historical/` are not authoritative and should not
be read or edited during normal work. They exist only for historical context
when a concrete question requires original rationale. When behavior changes,
update `dev-docs/AstichiSingleSourceSummary.md`, `docs/`, and tests/goldens;
do not maintain status, links, or wording inside archived docs unless the user
explicitly asks.

## Design rules

- Do not introduce enums without explicit project-owner approval. Do not work
  around this with magic strings, magic integers, sentinel strings, or other
  passive tags when the concept has semantics. Semantic concepts should be
  represented by objects/classes that can own behavior, validation, lowering,
  and documentation.

## Roll-build method

- When the user asks for a phased rollout using the roll-build method, start
  from a clean git tree and tag that point before implementation begins.
- Use the requested start tag name when one is given. If none is given, ask or
  use a clearly scoped phase-start tag name.
- An unqualified `roll-build` means: run all phases for that plan in sequence,
  committing and tagging each completed phase, and continue into the next phase
  without stopping unless the guardrails below require a pause.
- Implement one phase at a time.
- After a phase is complete, only commit and tag it if:
  - the phase goal is actually met
  - focused verification passes
  - the remaining ambiguities are minor and non-blocking
- If there are no more phases, or if confidence drops because of material
  ambiguity or instability, stop and wait instead of forcing the next phase.
- If work starts cycling on the same persistent bug or bug family, stop, report
  the cycle clearly, and ask for direction.

## When to push back on roll-build

- Push back when the next phase has too many unresolved ambiguities to produce a
  trustworthy checkpoint.
- Push back when the requested phase is too large or too coupled to complete
  safely as one checkpoint.
- Push back when implementation reveals facts that materially break the current
  design or plan assumptions.
- Push back when the resulting checkpoint would be misleadingly partial,
  unstable, or hard to recover from.

## Test-led semantics guardrail

- Do not change public semantics merely to make a test pass without updating the
  design/docs.
- If a red test implies a real semantic change rather than a bug fix or missing
  coverage, stop and update the design/docs before implementing the change.
- It is acceptable to tighten tests, fix assumptions, or fix correctness bugs
  that clearly match the current design intent.
- It is not acceptable to quietly redefine semantics to satisfy a convenient
  test expectation.

## Test coverage shape

- Prefer canonical fixture, golden, snapshot, or integration-style coverage for
  successful end-to-end behavior when the project already has that harness.
- Keep bespoke unit tests focused on narrow mechanics, recognition/parsing
  checks, edge-case failures, and diagnostics that the canonical harness cannot
  express cleanly.
- Avoid duplicating the same success-path assertions in both bespoke tests and
  canonical output tests; duplicated coverage increases maintenance cost without
  improving confidence.

## Test commands

- Focused tests: `uv run --with pytest pytest <test-path> -q`
- Full suite: `uv run --with pytest pytest -q`
- Python-version matrix: `uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q`
