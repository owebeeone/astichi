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

- Start with `dev-docs/V2StartHere.md`.

## Authoritative docs

For Astichi V2 work, use these docs:

- `dev-docs/V2StartHere.md`
- `dev-docs/AstichiCodingRules.md`
- `dev-docs/AstichiApiDesignV1.md` (base V1 design, still normative)
- `dev-docs/AstichiApiDesignV1-InsertExpression.md` (V1 addendum)
- `dev-docs/AstichiApiDesignV1-BindExternal.md` (V2 scope)
- `dev-docs/AstichiApiDesignV1-UnrollRevision.md` (V2 scope)
- `dev-docs/AstichiApiDesignV1-MarkerPreservingEmit.md` (V2 scope)
- `dev-docs/AstichiImplementationBoundaries.md`
- `dev-docs/V2Plan.md`
- `dev-docs/V2ProgressRegister.md`

V1 process docs (plan, progress register, deferred-feature list, issue log)
are archived under `dev-docs/historical/` and should not be edited.

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

## Test commands

- Focused tests: `uv run --with pytest pytest <test-path> -q`
- Full suite: `uv run --with pytest pytest -q`
