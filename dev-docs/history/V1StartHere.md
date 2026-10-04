# V1 start here

This is the process entry point for Astichi V1 work.

Use this document before starting implementation work and before declaring any
phase complete.

## 1. Get familiar with the docs

Read these first:

- `astichi/AGENTS.md`
- `astichi/dev-docs/AstichiCodingRules.md`
- `astichi/dev-docs/AstichiApiDesignV1.md`
- `astichi/dev-docs/IdentifierHygieneRequirements.md`
- `astichi/dev-docs/V1Plan.md`
- `astichi/dev-docs/AstichiImplementationBoundaries.md`
- `astichi/dev-docs/V1ProgressRegister.md`

You must be familiar with:

- roll-build terminology
- the phase-1 Astichi marker surface
- the additive-first builder model
- the identifier hygiene requirements and scope-collision rules
- source-authority and provenance rules
- implementation boundary rules

## 2. Confirm the next goal

Before starting work:

1. read `V1ProgressRegister.md`
2. identify the current active milestone/sub-phase
3. confirm the next goal from the progress register
4. if the progress register is unclear or you are unfamiliar with the current
   state, stop and confirm before proceeding

## 3. Review the execution structure

Before changing code:

1. identify which implementation layer owns the work
2. review `AstichiImplementationBoundaries.md`
3. determine the next course of action inside that layer
4. verify that the work does not improperly depend on a later layer

## 4. Phase completion rule

Before declaring a phase or sub-phase complete, verify strictly that:

- the goal is actually met
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

- update `V1ProgressRegister.md`
- record what was completed
- record what remains
- record the next concrete action
- record blockers or design issues immediately

## 6. Scope discipline

Astichi V1 should stay narrow.

Do not widen the scope casually. If implementation reveals a design problem:

- stop widening the mistake
- update docs/progress state
- correct the boundary before continuing
