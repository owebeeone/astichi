# F0c — Self-native threading and handle ownership

Status: companion to `FullSelfNativeRustAstPlan.md` slice **F0c**.

## Scope-owned engine

Production scopes own one native `EngineHandle` and a `NativeTemplateCache`. Template
registration and batch scope/materialize run against that engine until the scope
closes. Python facade code must not create ad hoc engines per composable on the hot
path.

## Threading policy (roll-build default)

Until a later slice documents otherwise:

1. **Preferred:** one `Scope` (and its native engine) per thread. YIDL lifecycle
   import and class materialization run on the main thread today; keep that
   invariant for F0c–F4.
2. **If shared:** `NativeTemplateCache` and native engine mutations must be
   synchronized on one lock per scope engine. Reads of immutable package snapshots
   may proceed without the lock; append/batch/materialize require it.
3. **Handles:** treat `EngineHandle`, `StateHandle`, and template handles as
   thread-confined. Cross-thread handle use is undefined and should fail stale-handle
   checks when detected.

## PyO3 external slots

External binding objects remain Python-owned. Native stores slot handles only.
Drop PyO3 references at scope/state teardown on the same thread that created the
scope, or under the scope engine lock if teardown is centralized.

## GIL

Parsing may release the GIL (`parsing_releases_gil`). Materialization does not in
the current extension. GIL-free materialize is out of scope for this roll-build
(see plan §H).

## Selection tiers

- **Hybrid** (`select_lower_engine`): requires
  `native.full_lower_engine.current_surfaces.v1` — current production default.
- **Self-native production** (`select_self_native_production_engine`): requires
  `native.self_native.current_surfaces.v1` — lifecycle production guards (F4+).

Do not satisfy production-path guards with hybrid-only capabilities.
