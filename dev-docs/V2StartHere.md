# V2 start here

This is the process entry point for Astichi V2 work.

Use this document before starting implementation work and before declaring any
phase complete.

V1 closed with the core lowering / hygiene / builder / materialize / emit
pipeline shipping. V2 extends the library with two feature families that were
designed during V1 but held back from implementation:

- **External bind** (`astichi_bind_external`) — compile-time parameterization
  of composables via `composable.bind(name=value)`.
- **Loop unroll** (V1-lite) — build-time unrolling of `astichi_for` loops with
  literal domains (including post-bind literals).

## 1. Get familiar with the docs

Read these first:

- `astichi/AGENTS.md`
- `astichi/dev-docs/AstichiCodingRules.md`
- `astichi/dev-docs/AstichiApiDesignV1.md` (normative base design)
- `astichi/dev-docs/AstichiApiDesignV1-InsertExpression.md` (addendum)
- `astichi/dev-docs/AstichiApiDesignV1-UnrollRevision.md` (V2 scope)
- `astichi/dev-docs/AstichiApiDesignV1-BindExternal.md` (V2 scope)
- `astichi/dev-docs/AstichiApiDesignV1-MarkerPreservingEmit.md` (V2 scope)
- `astichi/dev-docs/IdentifierHygieneRequirements.md`
- `astichi/dev-docs/AstichiImplementationBoundaries.md`
- `astichi/dev-docs/AstichiInternalsDesignV1.md`
- `astichi/dev-docs/V2Plan.md`
- `astichi/dev-docs/V2ProgressRegister.md`
- `astichi/dev-docs/V2DeferredFeatures.md`

You must be familiar with:

- roll-build terminology
- the V1 phase-1 Astichi marker surface (implemented and stable)
- the additive-first builder model
- the identifier hygiene requirements and scope-collision rules
- source-authority and provenance rules
- implementation boundary rules
- the V2 bind + unroll design addendums

## 2. Confirm the next goal

Before starting work:

1. read `V2ProgressRegister.md`
2. identify the current active phase / sub-phase
3. confirm the next goal from the progress register
4. if the progress register is unclear or you are unfamiliar with the current
   state, stop and confirm before proceeding

## 3. Review the execution structure

Before changing code:

1. identify which implementation layer owns the work (see
   `AstichiImplementationBoundaries.md`)
2. determine the next course of action inside that layer
3. verify that the work does not improperly depend on a later layer

## 4. Phase completion rule

Before declaring a phase or sub-phase complete, verify strictly that:

- the stated goal is actually met
- the required tests/verification for that layer pass
- the stated exit criteria are met
- the next stage can begin without any further development in the current stage

Do not mark a phase complete if:

- behavior still depends on unfinished work in the same phase
- the current layer has not produced its required handoff artifact
- the next phase would immediately need to re-open unfinished work from the
  current phase

## 5. Progress discipline

After each meaningful step:

- update `V2ProgressRegister.md`
- record what was completed
- record what remains
- record the next concrete action
- record blockers or design issues immediately

## 6. Scope discipline

V2 scope is deliberately narrow:

- external bind per `AstichiApiDesignV1-BindExternal.md`
- loop unroll per `AstichiApiDesignV1-UnrollRevision.md`
- marker-preserving emission per
  `AstichiApiDesignV1-MarkerPreservingEmit.md`
- Phase 3 polish (`V2Plan.md §5`): source-origin diagnostics (deferred
  §9.2), unified error-timing contract (§9.1), `compile_to_code`
  adapter (§7.4)

Out of scope for V2 (still deferred):

- any item in `V2DeferredFeatures.md §2` (the active V2-era tracker;
  this is the canonical out-of-scope list — consult it, not the
  frozen V1 list, before adding new work)

Do not widen the V2 scope casually. If implementation reveals a design problem:

- stop widening the mistake
- update docs/progress state
- correct the boundary before continuing

## 7. V1 history

V1 process docs (plan, progress register, deferred-feature list, issue log)
live in `historical/` for reference. They are frozen and should not be edited.
