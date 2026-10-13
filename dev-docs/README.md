# Developer Documentation

## Start Here

1. [Single-source summary](AstichiSingleSourceSummary.md): authoritative design
   and handoff.
2. [Coding rules](AstichiCodingRules.md): implementation rules.
3. [User documentation](../docs/) and [repository README](../README.md): current
   library usage, reference snippets, and goldens.

## Performance Work

[The performance index](perf-refactor/README.md) identifies the active native
hot-path plan and retained technical contracts. Older Python/hybrid/native
rollout documents and benchmark snapshots are grouped in history. Moving those
snapshots does not create a new performance result or certify an unfinished gate.

## Unimplemented Proposals

These remain proposals, not current behavior:

- [Python 3.11 compatibility plan](proposals/Python311CompatibilityPlan.md):
  accepted plan after Consistency/Safety GO; implementation has not started.
  [Review checkpoint](proposals/Python311CompatibilityPlan-ReviewCheckpoint.md).
  [Short design](proposals/Python311CompatibilityDesign.md) and
  [scope findings](proposals/Python311CompatibilityFindings.md) are later drafts.
  The first design review found a blocking reader-boundary defect; its
  [bounded redesign](proposals/Python311CompatibilityDesign-RemPlan-1.md)
  has focused closure evidence and awaits independent re-review.
- [Build resolver](proposals/AtichiBuildResolverProposal.md)
- [Builder identifier binding](proposals/AstichiBindBuilderDesign.md)
- [Import enhancements](proposals/AstichiImportProposedEnhancements.md)
- [Assembler concept context](proposals/AstichiAssemblerConcept.md)

## History

[History index](history/INDEX.md) groups old specifications, completed hole
support plans, superseded performance rollouts, and measured baselines.
`history/` replaces the former `historical/` directory; archived contents are
preserved, not promoted to active rules.

Keep summaries, current contracts, unfinished plans, and proposals discoverable
here. Move completed plans and superseded material to `history/`, repair current
links, and preserve historical evidence and revision-bound paths.
