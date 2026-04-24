# V2 Issues

This folder records issues carried forward beyond the closed V1 review set.

These are active issues for the current design/implementation cycle.

Current issues (ordered by priority):

- `006-cross-scope-identifier-threading.md` — **#1 blocking**:
  predictable identifier binding across Astichi scope boundaries
  (`astichi_import` / `astichi_pass`). Without this, `astichi_insert`
  shells cannot reliably read outer state or expose inner state, and
  users cannot reason about what names mean where. Everything else
  is subordinate.
- `005-definitional-name-replacement.md` — high priority, depends on
  006 (fills in the identifier-shape state grid per
  `AstichiCompositionModel.md`: `__astichi_arg__` undefined /
  `__astichi_keep__` defined / free, with builder-API peers,
  materialize gate + resolve + strip passes, and bindability from
  exported names into arg-identifier slots).
- `004-materialize-free-name-soundness.md` — high priority,
  intersects 006 (materialize may emit Python that raises
  NameError / UnboundLocalError even though the composable has no
  outstanding mandatory demands; Gap 4 resolved, Gaps 1–3 open;
  Gap 1 becomes the sanctioned gate for identifier crossings that
  lack 006's threading markers).
- `003-provenance-format-drift.md` — low priority.
