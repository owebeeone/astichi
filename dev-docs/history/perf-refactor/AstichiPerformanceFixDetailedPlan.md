# Astichi Performance Fix Detailed Plan

Status: detailed plan / proposal.

This document turns the performance findings in
`dev-docs/AstichiPerformanceAnalysisAndOptions.md` into an implementation plan.
The ordering is deliberately pragmatic: add measurement and safety rails first,
then take the largest low-risk runtime win, then move deeper into AST ownership,
single-pass merging, and cache-backed reuse.

The primary target is the YIDL decorator-runtime path: one call such as
`build_DataclassModule(container).emit_commented()` should stop spending seconds
rebuilding Astichi graphs after every contribution. YIDL generator time is a
secondary target.

## Goals

- Preserve the current public API surface unless a phase explicitly introduces
  an opt-in experimental surface.
- Make one decorator-runtime invocation fast before optimizing repeated test
  harness behavior.
- Keep source emission behavior stable for `emit()`, `materialize()`, and
  `emit_commented()`.
- Add direct AST execution coverage so future non-copying or cache-hit paths are
  tested by compiling and executing the generated AST, not just by comparing
  source strings.
- Add a generated-AST cache experiment with a pycache-style checked hash key, so
  repeated identical invocations can skip AST regeneration entirely.
- Avoid absolute filesystem paths in committed docs, tests, examples, or cache
  metadata fixtures.

## Non-goals

- Do not pickle generated classes as the primary cache artifact. Class pickles
  are import-name based in normal `pickle`, and dynamic class pickles are brittle
  across Python and source revisions.
- Do not weaken materialize gates for unresolved holes, external binds,
  identifier demands, or parameter holes.
- Do not make provenance carry hidden builder or cache semantics. Source remains
  authoritative.
- Do not depend on cache hits for correctness. Every cache miss must produce the
  same observable result.

## Stage 0: Measurement and Safety Baseline

Purpose: lock down the current problem shape before optimizing.

Implementation:

- Add a repeatable benchmark script or pytest-marked perf scenario under
  `docs/validation/perf/`.
- Measure these phases separately:
  - YIDL parse and concept compile.
  - `emit_concept_runtime_source`.
  - `exec(decorator_source, namespace)`.
  - container construction.
  - `build_DataclassModule(container)`.
  - `.emit_commented()`.
  - direct AST compile/exec once that surface exists.
- Add lightweight counters around:
  - `AssemblyScope._refresh_inventory`.
  - `BuilderHandle.build`.
  - `materialize.api.build_merge`.
  - `_make_block_insert_shell`.
  - `copy.deepcopy` count or cumulative time if practical.

Tests and checks:

- Add a focused regression test for the assembler scope that proves the current
  high-level behavior remains stable while counters are present only in test or
  validation code.
- Keep perf checks out of the normal fast unit suite unless they assert call
  counts, not wall time.

Acceptance:

- A checked-in command can reproduce the split dataclass profile shape.
- The baseline records call counts and wall times without changing production
  behavior.

## Stage 1: Incremental Inventory in `AssemblyScope`

Purpose: remove the dominant quadratic rebuild loop.

Current behavior:

- `AssemblyScope.add(...)`, `scope.apply(...)`, external binds, and identifier
  binds call `_refresh_inventory()`.
- `_refresh_inventory()` calls `self.builder.build(unroll=False).inventory`.
- This runs a full `build_merge` after almost every contribution just to read
  inventory.

Implementation:

- Add an incremental inventory update API around `Inventory` and
  `MutableInventory`.
- Replace `_refresh_inventory()` with event-specific updates:
  - adding a root instance prefixes that composable inventory under the root
    build path
  - adding a composable contribution prefixes the source occurrence inventory
    under the target build path plus source instance name
  - satisfying an external value removes the matched `external.bind` occurrence
  - satisfying an identifier demand removes the matched `identifier.demand`
    occurrence and updates any affected keep/arg binding metadata needed by
    later candidate selection
- Keep a slow verification mode that rebuilds inventory from `build_merge` and
  compares it with incremental inventory during development.
- Preserve diagnostic locality: candidate errors should still identify the same
  demand/resource records and source locations.

Important design detail:

- The inventory update path must represent occurrence records, not just source
  composable records. A reusable source composable can be inserted several times
  under different build paths and orders.
- Record ids must be stable enough for deterministic diagnostics. If current
  `Root/Step/#1` style ids are not sufficient for repeated indexed
  contributions, define a stable occurrence id scheme as part of this stage.

Tests and checks:

- Unit tests for inventory delta operations.
- Assembler scope tests comparing incremental inventory snapshots to the old
  full-rebuild inventory on small graphs.
- YIDL split dataclass validation with a counter asserting that inventory
  refreshes no longer call `build_merge`.
- Existing diagnostic tests must keep equivalent messages or intentionally
  updated messages with better source context.
- After Stage 6 lands, include this path in AST execution parity tests.

Acceptance:

- One valid split dataclass decorator-runtime invocation drops from hundreds of
  `build_merge` calls to the real final production builds only.
- No cache is required to see the speedup.
- Full Astichi tests pass.

## Stage 2: AST Ownership, Copy Reduction, and Shell Memoization

Purpose: reduce the residual cost after the quadratic inventory rebuild is gone.

Current hot spots include:

- `copy.deepcopy(record.composable)` at the start of `build_merge`.
- `copy.deepcopy(source_tree.body)` when collecting block contributions.
- `_make_block_insert_shell(...)` deep-copying every contribution body again.
- `BasicComposable.bind(...)` and `bind_identifier(...)` copying whole trees for
  small substitutions.

Implementation:

- Define explicit AST ownership states:
  - source-owned immutable template
  - builder-owned mutable working tree
  - returned caller-owned executable tree
  - cache-owned serialized snapshot
- Make copying happen at ownership boundaries rather than mechanically at every
  helper call.
- Introduce lazy or copy-on-write binding wrappers for external and identifier
  substitutions where validators can still see resolved names before they need
  them.
- Memoize block insert shell construction only when the shell body is guaranteed
  not to be mutated later, or memoize a serialized/frozen shell snapshot and
  hand out fresh owned copies.
- Audit in-place mutators before sharing any node:
  - source-location propagation
  - hygiene renaming
  - insert ref prefixing
  - keep marker injection
  - external bind rewriting
  - identifier demand rewriting

Tests and checks:

- No-copy/COW tests must execute generated ASTs, not just compare emitted text.
  If this stage ships before the public Stage 6 surface, add a private test
  helper that compiles the final materialized AST directly.
- Add aliasing tests:
  - the same source composable inserted twice with different bindings produces
    independent runtime behavior
  - repeated builds from the same builder produce the same result
  - mutating one returned AST does not affect another returned AST
  - a failed build does not poison a later successful build
- After Stage 7 lands, add cache-hit aliasing tests to ensure cache-owned nodes
  cannot be mutated by materialize or execution.

Acceptance:

- Residual `copy.deepcopy` time is materially lower in the profiler.
- All AST execution parity and aliasing tests pass.

## Stage 3: Batched Merge Pipeline

Purpose: stop running per-contribution AST passes when one pass over the final
union is enough.

Implementation:

- Refactor `build_merge` from a contribution-at-a-time pipeline to a
  union-at-a-time pipeline.
- Collect all edges and contributions into a normalized merge plan.
- Perform these operations once over the planned union:
  - marker recognition
  - target replacement
  - parameter payload extraction
  - expression insert extraction
  - source-location propagation
  - demand/supply extraction
  - inventory construction
  - hygiene analysis and rename
- Keep target validation and diagnostics precise by carrying source contribution
  metadata through the plan.

Tests and checks:

- Golden source output must remain stable unless a deliberate formatting or
  diagnostic improvement is documented.
- Inventory descriptor snapshots must remain equivalent.
- Add edge-order tests for equal and unequal contribution order.
- Add diagnostics for unknown target, wrong payload shape, duplicate parameter,
  duplicate keyword, and unresolved demand.
- After Stage 6 lands, run AST execution parity against batched merge output.

Acceptance:

- One real final `build_merge` is substantially faster than the post-Stage-1
  final merge.
- Per-contribution AST walk count is replaced by per-final-tree walk count in
  profiler evidence.

## Stage 4: Defer Provenance and Hygiene Work to Finalization

Purpose: avoid paying final-output costs before a final output is requested.

Implementation:

- Separate "build a composable graph result" from "finalize for source or
  execution".
- Defer provenance propagation, comment rendering support, and hygiene closure
  until:
  - `materialize()`
  - `emit()`
  - `emit_commented()`
  - `to_executable_ast()`
- Preserve behavior for callers that currently inspect materialized composables.
- Ensure cache keys include finalization policy, because executable AST,
  comment-preserving AST, and provenance-bearing source may be observably
  different once Stage 7 introduces persistent cache artifacts.

Tests and checks:

- Source emission tests continue to pass.
- Diagnostics still report actionable source locations.
- After Stage 6 lands, AST execution parity runs for finalized executable ASTs.
- A build that is never emitted should not perform comment-rendering-only work.

Acceptance:

- Build-only consumers pay less than source-emitting consumers.
- Finalized output remains behaviorally identical.

## Stage 5: Build Resolver / Declarative Assembly Plan

Purpose: replace graph mutation plus repeated lookup with an explicit assembly
plan that can be materialized once.

This stage aligns with `dev-docs/AtichiBuildResolverProposal.md` and is the
long-term cleaner model for generator workloads.

Implementation:

- Add source-only definitions if still needed for generator palettes.
- Introduce a normalized build resolver that produces:
  - live instance records
  - live edges
  - output root names
  - source metadata for diagnostics
- For YIDL, move toward generating a concrete assembly plan rather than driving
  `AssemblyScope` by mutating a builder after every contribution.
- Keep existing `builder.add` behavior compatible.

Tests and checks:

- Existing builder tests must pass unchanged.
- New tests for source-only definitions:
  - unused source-only definitions do not emit or reject
  - live source-only definitions validate normally
  - root-capable definitions preserve current multi-root behavior
- YIDL split dataclass remains a canonical integration test.
- After Stage 6 lands, AST execution parity runs through the resolver path.

Acceptance:

- Generator palettes no longer require conditional registration gymnastics.
- YIDL can choose a plan-emitting runtime without losing Astichi diagnostics.

## Stage 6: Direct AST Execution Parity Surface

Purpose: prove generated ASTs can be executed directly and build the test
surface needed for no-copy and cache phases.

This stage does not fix the original 20+ second AST generation cost by itself.
It removes source emission from execution-oriented consumers and establishes
correctness tests that execute generated ASTs.

Implementation:

- Add an internal or experimental API that returns an owned executable AST for a
  fully materialized composable, for example `to_executable_ast()` on
  `BasicComposable` or a helper in `materialize.api`.
- The returned AST must be safe for the caller to compile and mutate without
  corrupting the composable or any cache entry.
- Add an internal helper for execution tests:

  ```python
  tree = composable.materialize().to_executable_ast()
  code = compile(tree, "<astichi-generated>", "exec")
  namespace = {}
  exec(code, namespace)
  ```

- Initially this can deep-copy the final tree. Earlier ownership work may make a
  cheaper implementation possible, but the API contract must remain "caller owns
  the returned tree".

Tests and checks:

- For representative golden cases, execute both:
  - emitted source via `exec(compile(source, ...))`
  - generated AST via `exec(compile(tree, ...))`
- Assert the same runtime behavior, not only the same source text.
- Include cases covering:
  - block holes
  - expression holes
  - function argument payloads
  - parameter holes
  - managed imports
  - comments through `emit_commented()` where source text is still needed
- Add mutation isolation tests:
  - build a composable
  - request its executable AST
  - mutate the returned AST
  - request/build again
  - execute the second result and verify it is unaffected

Acceptance:

- Current focused and full Astichi tests pass.
- AST execution parity passes on the canonical successful golden cases.
- Mutation of a returned AST cannot affect subsequent builds.

## Stage 7: Generated AST Cache Experiment

Purpose: determine how much repeated identical invocations can gain by skipping
AST regeneration entirely.

This is an opt-in cache experiment. It is not a substitute for fixing the
single-invocation merge cost, but it can be a useful relief valve for stable
generated decorators and repeated containers.

Cache artifact:

- Cache an executable AST snapshot or a final materialized AST snapshot, not a
  generated class object.
- Store the AST with `pickle` only as a trusted local build artifact. Loading a
  cached AST is code-equivalent and must never be treated as safe for untrusted
  inputs.
- Every cache hit must return a fresh owned tree, either by unpickling a new
  object graph or by deep-copying an immutable in-memory cached tree before
  handing it to callers.

Cache key design:

- Use a checked-hash model similar to hash-based pyc invalidation from PEP 552:
  the cache is valid only when a deterministic hash of the semantic inputs
  matches the stored manifest.
- Do not use mtimes as the correctness signal. Mtimes may be recorded for
  diagnostics only.
- Include a cache header or manifest with:
  - Astichi cache format version.
  - Astichi package version and, in editable checkouts, an optional source-tree
    fingerprint.
  - Python implementation name.
  - `sys.implementation.cache_tag`.
  - `importlib.util.MAGIC_NUMBER` or equivalent bytecode compatibility marker.
  - Python major/minor version.
  - AST cache schema version.
  - Materialize and emit policy flags.
  - `unroll` option.
  - Comment preservation policy.
  - Provenance policy if source emission is part of the cached result.
  - A canonical fingerprint of the builder graph or YIDL assembly plan.
  - A canonical fingerprint of all source snippets, including logical
    `file_name`, `line_number`, `offset`, `source_kind`, `arg_names`, and
    `keep_names`, because those can affect diagnostics, provenance, hygiene, or
    emitted comments.
  - A canonical fingerprint of the container records used by the YIDL assembly.
- Prefer a deterministic JSON or msgpack manifest plus a SHA-256 or BLAKE2 hash
  over pickling the key itself.
- Store only logical or repository-relative source names in fixtures and
  manifests. Do not store absolute paths.

Cache write/read behavior:

- Write cache files atomically: write to a temporary sibling, fsync when
  practical, then replace.
- Treat corrupt, missing, version-mismatched, or hash-mismatched cache entries
  as misses.
- Never allow cache load failures to change user-visible generation behavior
  except for diagnostics in an explicitly verbose mode.
- Keep the cache location configurable. Suggested defaults:
  - project-local ignored directory such as `.astichi-cache/`
  - caller-provided cache directory
  - disabled by default until the experiment is validated

Tests and checks:

- Cache hit and miss tests:
  - identical inputs hit
  - source text change misses
  - logical source-location change misses when comments/provenance can observe it
  - `unroll` option change misses
  - Python cache tag mismatch misses
  - Astichi cache schema mismatch misses
  - corrupt payload misses
- AST execution tests must run both a cold result and a cache-hit result.
- Mutation isolation tests must run against a cache-hit AST.
- Add a validation benchmark comparing:
  - cold build to AST
  - warm in-process cache hit
  - warm disk cache hit
  - source emit from cached AST
  - direct `compile(ast_tree, ..., "exec")` from cached AST

Acceptance:

- Cache is opt-in, deterministic, and correctness-neutral.
- Warm cache hits avoid `build_merge` entirely for the cached assembly result.
- Cache-hit ASTs execute with the same runtime behavior as cold ASTs and emitted
  source.

## Stage 8: YIDL-Specialized Runtime Path

Purpose: after Astichi is fast enough, remove remaining generic interpreter
overhead from generated decorators.

This stage mostly belongs to YIDL, but Astichi should expose the APIs needed for
it.

Implementation direction:

- Keep generated API functions such as `build_DataclassModule(container, *,
  unroll="auto")`.
- Generate specialized production functions instead of a large
  `ASSEMBLY_*` metadata blob plus generic `run_assembly(...)`.
- Use Astichi as the template parser, validator, and final materializer, not as
  the repeated hot-path assembly interpreter.
- Prefer direct AST or code-object execution when source text is not requested.

Tests and checks:

- YIDL golden outputs remain stable.
- Generated decorators run both source-emission and direct-AST execution tests.
- Stage 7 cache key construction includes the generated runtime version so
  specialized runtime changes invalidate older cache entries.

Acceptance:

- Remaining runtime is proportional to actual container records and final output
  size, not to generic metadata interpretation overhead.

## Cross-Stage Verification Matrix

Every implementation stage that changes build/materialize behavior should run:

- Focused Astichi tests for the touched subsystem.
- `uv run --with pytest pytest -q` from the Astichi repo before finalizing.
- YIDL split dataclass validation when a stage touches assembler or materialize
  behavior.
- AST execution parity tests from Stage 6 once available. Before Stage 6 lands,
  any stage that changes AST ownership must add a private direct-AST execution
  helper rather than relying only on emitted source text.
- Cache-hit execution tests after Stage 7.

For stages that change AST copying or ownership, also run:

- repeated build tests
- returned AST mutation tests
- cache-hit returned AST mutation tests after Stage 7
- same-template-multiple-bindings tests
- failed-build-does-not-poison-cache tests

## Expected Performance Milestones

These are engineering targets, not correctness requirements:

- Stage 1: remove the hundreds of throwaway `build_merge` calls. Expected
  decorator-runtime speedup: roughly one order of magnitude on the split
  dataclass workload.
- Stage 2: reduce residual copy cost. Expected additional speedup depends on how
  much copying remains after Stage 1.
- Stage 3: make the final merge closer to one pass over the final AST.
- Stage 4: make build-only and direct-execution consumers avoid source-only
  finalization cost.
- Stage 5: give generator workloads a cleaner one-plan materialization model.
- Stage 6: make direct AST execution a supported and tested output path.
- Stage 7 cache hit: repeated identical invocations should bypass AST
  generation and approach deserialize plus optional `compile(ast, ..., "exec")`
  cost.
- Stage 8: YIDL generated decorators should stop paying generic assembly
  interpreter overhead on hot paths.

## Rollout Guidance

- Keep each stage independently shippable.
- Do not combine Stage 1 incremental inventory with Stage 2 no-copy mechanics in
  one change. The failure modes are different and need separate tests.
- Keep the cache opt-in until it has cold/hot benchmarks, invalidation tests, and
  mutation isolation tests.
- Prefer correctness counters over wall-time assertions in unit tests.
- Record benchmark results in validation docs, not in fragile test thresholds.
