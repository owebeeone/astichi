# V3 Issues

This folder records issues opened for the V3 composition cycle.

These are not historical notes. They are active design and implementation
problems that block the next stage of compositionality.

Current issues (ordered by priority):

- `001-deep-descendant-cross-composable-addressing.md` — **blocking**:
  composition cannot scale past root-instance-first wiring while built
  composables hide their internal structure. V3 needs a descendant/reference
  addressing model so later stages can target or source names below the top
  level of a stage-built composable.
