# Build Operations Analysis

Status: detailed design draft.

This document describes the hot operations for the Python lower engine and the
eventual native engine. The goal is to expose the algorithmic pressure points
before code is sliced.

## Current Hot Shape

The current `AssemblyScope` path repeatedly:

1. applies one candidate;
2. mutates the builder graph;
3. binds or rebuilds a `BasicComposable`;
4. refreshes occurrence inventory;
5. freezes a Python `Inventory`;
6. searches the projected inventory again.

This is correct but too expensive. The target design keeps assembly as table
updates over lower handles until materialization is explicitly requested.

## Operation Summary

| Operation | Current shape | Target Python shape | Target native shape |
| --- | --- | --- | --- |
| register surface bundle | implicit Python code paths | build registry from semantic surface specs | consume same canonical bundle and assign dynamic ids |
| register template | scan AST, build Python inventory | `astichi.compile(...)` registers a lower template and returns a lower-backed composable | native parser builds native AST/IR and stores it behind the same lower composable facade |
| add root | builder add plus inventory prefix/rebuild | append occurrence, expose derived records | append occurrence, update vectors/bitsets |
| find candidates | iterate projected `Inventory` records | query lower indexes, filter live records | query compact indexes, bitset/live filter |
| apply composable | add builder edge, prefix source inventory | append source occurrence and edge | append occurrence/edge, update indexes |
| apply external | `BasicComposable.bind`, clone AST | overlay external slot on occurrence | overlay external slot, no Python AST clone |
| apply identifier | `bind_identifier`, clone AST | overlay identifier binding on occurrence | overlay identifier binding, no Python AST clone |
| build/materialize | reconstruct from builder graph | lower materialization plan, then output | same plan, native execution if enabled |
| inventory print | already materialized Python object | projected snapshot only | bulk snapshot then Python formatting |

## Register Surface Bundle

Surface registration happens before template registration. It makes the active
set of hole/production surfaces explicit and assigns dynamic ids for hot-path
tables.

Input:

```text
surface specs
AST pattern descriptors
operation descriptors
compatibility rules
diagnostic descriptors
schema version
bundle_signature
```

Output:

```text
SurfaceBundleHandle
SurfaceId table
OperationId table
PatternId table
registered surface/pattern/operation handles stored on Python specs
stable-key mapping for snapshots
```

Expected complexity:

- O(S + P + O + C) for surfaces, patterns, operations, and compatibility rules;
- startup or engine-initialization cost only;
- no per-candidate Python callback in native code.

Hot points:

- dynamic ids are process-local handles returned by registration and stored on
  Python specs; snapshots write stable keys;
- native operations after registration receive handles, not pattern names;
- the engine rejects handles from a different engine instance or surface bundle;
- `bundle_signature` is a serialized/cache guard only; it is not used to
  synchronize hot-path native calls;
- template records store surface ids after registration;
- each registered pattern names one consolidated pattern template;
- diagnostic-only/reserved patterns are registered so diagnostics stay
  centralized but do not produce assembly records;
- candidate lookup asks the registry for compatibility instead of switching over
  a fixed list of hole types;
- materialization emits an operation stream over registered operation ids.

This is the resilience point for future syntax. Adding `match`/`case`,
exception handlers, loop `else`, or `finally` should add registered specs and
goldens. It should not add new native API entry points unless the surface
requires a genuinely new operation primitive.

## Register Template

Input:

```text
Composable source tree
source text when available
recognized markers
demand/supply ports
origin/source metadata
registered surface bundle
```

Output:

```text
TemplateId
TemplateRecord list
target indexes
materialization metadata
scope metadata
surface ids on records
```

Hot points:

- AST scanning is allowed here because registration is per template, not per
  assembly edge.
- `astichi.compile(...)` should end here with a lower-backed composable facade,
  not with CPython AST as the authoritative template representation.
- Target and locator metadata must be complete enough for later materialization.
- Do not rely on later Python AST rescans to recover hole shape, owner scope, or
  ref-path information.
- AST pattern descriptors should drive new surface recognition so adding syntax
  surfaces does not add central template-registration branches.

Python implementation:

- reuse existing marker recognition and inventory extraction initially;
- lower the result into template records;
- assign registered surface ids to target and production records;
- cache by composable identity or stable template key only after correctness is
  established.

Native implementation:

- accept pre-extracted metadata from Python first, or mirror extraction after a
  separate profiling gate;
- consume the same registered surface bundle as the Python engine;
- hold source text, template AST/source tokens, or native AST IR references as
  required by the selected native backend;
- avoid per-record Python callback during registration once metadata is known.

## Add Root Occurrence

Target algorithm:

```text
template_id = register_template(composable)
build_path_id = intern_build_path(parent=ROOT, segment=name)
occurrence_id = append_occurrence(template_id, build_path_id)
expose live records for occurrence
add index entries for visible records
```

Expected complexity:

- O(R) for records in the added template;
- no AST clone;
- no full inventory freeze;
- no old builder graph rebuild.

Hot point:

The O(R) index update is acceptable because a newly visible occurrence exposes
new records. It must not become O(total_records) across the whole scope.

## Candidate Lookup

Candidate lookup should use direct lower queries.

```text
find_candidates(resource, selector):
  resource_descriptor = lower_resource(resource)
  candidate_record_ids = index_lookup(resource_descriptor, selector.name)
  filtered = filter_live_and_selector(candidate_record_ids, selector)
  return compatibility_filter(filtered, resource_descriptor)
```

For composable resources, compatibility compares production records from the
resource template with candidate hole records.

For external values and identifiers, compatibility checks demand kind and name.
For all syntax surfaces, compatibility is resolved through registered surface
rules and their shape predicates. Core lookup should not know whether a target
is a block hole, elif clause, match case, exception handler, or loop `else`.

Expected complexity:

```text
O(index_bucket_size + compatibility_checks)
```

It must not be:

```text
O(total_scope_records + Python Inventory projection)
```

Python hot points:

- keep candidate objects lightweight;
- avoid building `InventoryRecord` projections unless formatting diagnostics;
- same-site binding collapse in YIDL should use candidate record handles or a
  stable candidate key, not a full `InventoryRecord`.

Native hot points:

- return candidate batches in bulk;
- avoid constructing Python candidate wrappers until YIDL actually needs one;
- expose stable candidate keys for grouping and diagnostics.

## Apply Composable Candidate

Target algorithm:

```text
target = candidate.target_record_id
source_template = candidate.resource.template_id
target_occurrence = occurrence_for_record(target)
source_path = child_build_path(target_occurrence.build_path, resource.instance_name)
source_occurrence = append_occurrence(source_template, source_path)
edge = append_edge(target, source_occurrence, order, overlay)
if target is single-add hole:
  mark target satisfied
expose source occurrence records
```

Expected complexity:

- O(R_source) for source records newly exposed;
- O(1) for edge append;
- O(1) or bitset update for satisfying the target;
- no source AST clone;
- no Python builder graph mutation on the hot path.

The single-add hole rule is important: a satisfied scalar hole should disappear
from candidate lookup without rebuilding maps. Keep the record in the table and
filter it through live/satisfied state.

## Apply External Or Identifier Candidate

Target algorithm:

```text
target = candidate.demand_record_id
owner_occurrence = owner_for(target)
overlay = overlay_for(owner_occurrence)
new_overlay = append_overlay_binding(overlay, target.name, value_or_identifier)
set occurrence overlay to new_overlay
mark demand satisfied when the demand is single-use
```

Expected complexity:

- O(1) overlay append for small overlay maps;
- O(log N) or O(1) interner work for symbol/value slots;
- no AST clone;
- no eager `BasicComposable.bind` or `bind_identifier`.

Python external values remain in a facade object table keyed by
`ExternalSlotId`. The lower engine owns the binding relationship and validation
state.

## Materialization Plan Construction

Materialization is lower-layer work.

Target algorithm:

```text
root = choose live output occurrence
walk occurrence graph in deterministic edge order
resolve insert operations from target records and source productions
apply overlays to occurrence payloads
build scope graph
compute hygiene decisions
produce marker gates and final artifact requests
emit an operation stream over registered operation ids
emit a hygiene stream over registered hygiene operation ids
```

Expected complexity:

```text
O(live_occurrences + live_edges + materialized_nodes)
```

It must not include candidate lookup or repeated inventory merge. If
materialization remains hot after Phase 2, the profile should show pure
materialization work, not hidden assembly bridge work.

Python hot points:

- reuse existing materializer internals behind lower API where practical;
- avoid repeatedly converting lower state into a legacy builder graph;
- expose materialization-plan snapshots before producing final AST/source.

Native hot points:

- avoid crossing into Python for every insert operation;
- parse and transform against a native AST/IR when the native AST probe proves
  that path worthwhile;
- construct `_ast` objects in bulk only at the final materialized artifact
  boundary, or emit a validated artifact accepted by the facade;
- measure CPython AST node construction, required/default field population, and
  location metadata population separately;
- use public `ast`/`_ast` construction plus public `compile(...)` as the default
  artifact boundary;
- keep external value lookup slot-based;
- support registered operation primitives generically; reject native engine
  selection before work starts if the active surface bundle needs an unsupported
  primitive.

## Future Surface Addition

Adding a syntax surface should follow this operational path:

```text
define semantic surface class
define authored and emitted AST patterns
define target and production record builders
define compatibility rules
define lowering operation descriptors
register the surface bundle
add structural and final goldens
```

The core add/apply/candidate algorithms should remain unchanged. If a new
surface needs only existing operation primitives, the native API should not
change. If it needs a new primitive, the primitive is added deliberately to the
shared operation vocabulary and covered by Python/native parity goldens.

## Debug Inventory Projection

Projection is not a hot operation.

Target algorithm:

```text
snapshot = lower_engine.debug_inventory_snapshot(state)
Inventory = facade.project_inventory(snapshot)
```

Acceptance:

- candidate lookup does not call projection;
- `scope.inventory` may call projection for compatibility;
- projection time is measured separately;
- inventory printing uses deterministic snapshot formatting.

## Structural Snapshot

The structural snapshot is the canonical intermediate verification artifact.

Target algorithm:

```text
snapshot = lower_engine.structural_snapshot(state)
text = canonical_snapshot_writer(snapshot)
round_tripped = canonical_snapshot_reader(text)
assert canonical_snapshot_writer(round_tripped) == text
```

Hot point:

Snapshot writing is not the hot path. It can allocate Python objects, but it
must reflect lower state directly and must not materialize AST output to prove
intermediate assembly correctness.

## Counters

Every implementation slice should keep these counters visible:

- template registrations;
- occurrences appended;
- edges appended;
- overlays appended;
- candidate lookup count/time;
- candidate batch size;
- debug inventory projection count/time;
- structural snapshot count/time;
- surface bundle registration count/time;
- unsupported native operation count;
- materialization-plan count/time;
- final materialization count/time;
- legacy builder adapter count/time, if any;
- `_rebuild_composable` calls during scope apply;
- `_replace_occurrence_inventory` calls during scope apply.

The hard Phase 2 gate is zero per-apply composable rebuild and zero hot-path
inventory replacement for the YIDL assembly path.
