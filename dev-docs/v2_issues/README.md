# V2 Issues

This folder records issues carried forward beyond the closed V1 review set.

These are active issues for the current design/implementation cycle.

Current issues:

- `003-provenance-format-drift.md` — low priority
- `004-materialize-free-name-soundness.md` — high priority (materialize
  may emit Python that raises NameError / UnboundLocalError even
  though the composable has no outstanding mandatory demands)
