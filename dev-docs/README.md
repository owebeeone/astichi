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

- [Python 3.11 compatibility plan](proposals/Python311CompatibilityPlan.md) and
  [short design](proposals/Python311CompatibilityDesign.md): scope narrowed by
  the user on 2026-10-14 to same-version provenance and explicit 3.11 skips for
  Pyrolyze integrations. Implementation has not started. The
  [plan review checkpoint](proposals/Python311CompatibilityPlan-ReviewCheckpoint.md)
  and [design review checkpoint](proposals/Python311CompatibilityDesign-ReviewCheckpoint.md)
  preserve the earlier broader reviews; they do not certify this amendment.
  The [scope finding](proposals/Python311CompatibilityFindings.md) is retained
  for separate Pyrolyze work, not an Astichi prerequisite.
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
