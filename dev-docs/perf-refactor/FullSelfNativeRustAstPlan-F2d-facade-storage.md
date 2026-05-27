# F2d — Facade storage (partial)

Status: tag `rust-fsn/f2d-facade-storage`.

## Landed

- `composable_template_tree_for_builder()` in `lower_engine/facade.py` projects
  template AST from the native workspace when a composable has `native_source`.
- Counter: `native_facade_builder_tree_projection`.

## Not wired yet

Builder `build()` still uses `clone_ast(composable.tree)` for shell indexing.
Switching the default path regressed `comment_marker.py` goldens (native workspace
copy does not yet preserve comment-marker materialization parity).

Next: wire projection after native comment/emit parity (F4c surface row).
