# Structural Inventory Design

Status: detailed design draft.

This document defines the lower-engine data model for the inventory-first
assembly refactor. The model has one contract shared by the Python reference
engine and the later native engine.

## Objectives

The data structures must make the common assembly path cheap:

1. register source templates once;
2. add occurrences by handle;
3. satisfy holes by adding edges or overlays;
4. query candidates through indexes;
5. produce materialization plans and final artifacts only when requested;
6. project Python `Inventory` objects only for diagnostics, compatibility, and
   tests.

The AST remains a source template payload. It is not the assembly state.

## Shared Handle Model

The lower engine should use compact handles for hot state. Python may represent
them as small dataclasses or integers. A native backend should represent them as
integer indices into arena-owned tables.

```text
TemplateId
TemplateRecordId
OccurrenceId
RecordId = (OccurrenceId, TemplateRecordId)
BuildPathId
ScopeId
LocatorId
SymbolId
OverlayId
EdgeId
ExternalSlotId
IdentifierId
SurfaceId
OperationId
PatternId
```

These are semantic handles, not a fixed public category system.
Record/resource behavior must still live on semantic descriptor objects or
generated semantic tables.
Serialized snapshots may use stable names for readability, but implementation
logic should not rely on unowned string tags.

`SurfaceId`, `OperationId`, and `PatternId` are assigned dynamically when the
active Astichi surface bundle is registered. They are hot-path handles, not
golden identities. Structural snapshots must write stable surface and operation
keys plus schema versions.

## Surface Extension Registry

The lower engine must not hardcode the full set of Python syntax surfaces.
Block holes, expression holes, parameter holes, elif clauses, and future
surfaces such as match cases, exception handlers, loop `else`, and `finally`
blocks should all register through one surface-extension contract.

The registry is shared by the Python lower engine and the later native engine:

```text
SurfaceRegistry:
  surface_specs
  operation_specs
  pattern_specs
  dynamic_id_tables
  registered_handles
  schema_version
  bundle_signature
```

A surface spec describes:

```text
SurfaceSpec:
  surface_key
  version
  authored_patterns
  emitted_patterns
  target_record_builder
  production_record_builder
  compatibility_rules
  shape_predicate_descriptors
  ordering_policy
  default_policy
  lowering_operations
  validation_timing
  diagnostics
  snapshot_fields
```

The Python implementation should build this from behavior-owning semantic
classes. The native implementation should receive a canonical lowered bundle as
input. The native API should remain generic: register a surface bundle,
register templates, query candidates, apply candidates, build materialization
plans, and emit snapshots. It should not grow one entry point per surface.

Registration is a binding step. The native engine returns handles for each
accepted surface, pattern, and operation, and Python stores those handles on the
registered specs. Later native calls use the handles, not stable string keys. The
engine must reject a handle that was not produced by the active engine instance
and surface bundle.

Future surfaces should normally require only a new surface spec and goldens when
they lower to existing operation primitives. Native changes are expected only
when a surface needs a new primitive operation or a new lifetime/ownership rule.

See `dev-docs/perf-refactor/SurfaceExtensionContract.md` for the full
extension contract.

## Template Catalog

A template is the immutable metadata extracted from a composable source tree.
Registering a template precomputes all data needed by assembly and later
materialization.

```text
Template:
  template_id
  surface_bundle_id
  source_tree_ref
  origin_summary
  source_locator_table
  scope_table
  template_records
  target_index
  production_index
  identifier_demand_index
  external_demand_index
  materialization_metadata
```

`source_tree_ref` is Python-owned in the reference engine. A native backend
should prefer source text, a native parsed tree, or a normalized Astichi AST IR
as its working template graph. It may hold a strong `PyObject*` reference to the
Python AST only as a compatibility token, not as the native transform graph.

`template_records` are record prototypes. They do not include build-path or
occurrence state. They include:

```text
TemplateRecord:
  template_record_id
  surface_id
  semantic_resource
  logical_name_id
  source_locator_id
  owner_scope_id
  payload_ref
  materialization_role
```

`semantic_resource` should be a behavior-owning semantic object in Python. A
native implementation can mirror it with a generated semantic table only after
that table has a schema version and content signature.

`surface_id` connects the record to the registered target or production
surface. Candidate lookup should ask the registry whether a production surface
can satisfy a target surface. It should not switch over a fixed list of hole
families.

## Native AST Source And Final Artifact Boundary

The native backend should not use CPython AST nodes as its working graph unless
the native AST probe proves that wrapping them is still faster and simpler. The
preferred native path is:

```text
source text
  -> native parser
  -> native AST or normalized Astichi AST IR
  -> template records, locators, and operation metadata
  -> native materialized artifact
  -> final CPython ast/_ast node construction
```

The GIL-free opportunity is in native parse, inventory extraction, transform,
materialization-plan construction, and hygiene. CPython AST node construction is
allowed at the final boundary, where the facade can pass the returned module to
`compile(...)` and then `exec(...)` when executable output is requested.

The shared native contract should target public CPython `ast`/`_ast`
construction plus public `compile(...)`. Internal CPython compiler APIs such as
`PyArena` or `_PyAST_Compile` are not part of the baseline contract. They may be
investigated only as a separate backend spike because they are version-sensitive
and not stable enough for the shared lower-engine boundary.

The Python reference engine can continue to use Python `ast` objects directly.
The shared correctness contract is not object identity with Python `ast`; it is
template records, locators, operation streams, structural snapshots, and final
golden parity.

## Compile Facade And Composable Boundary

`astichi.compile(...)` should become a facade entry point into the lower module.
It should parse/register a template and return a composable facade backed by a
lower `TemplateId`, not a Python AST object as the authoritative representation.

```text
astichi.compile(source, options)
  -> lower_engine.register_template(...)
  -> LowerComposable
```

For the Python lower engine, registration may still parse with Python `ast` and
store a Python source tree reference behind the template. For a native lower
engine, registration should use the native parser and wrap the resulting native
AST/IR template in the same lower composable facade.

```text
LowerComposable:
  engine_handle
  template_id
  source_summary
  facade_metadata
  artifact_copy_api
```

There should be one facade composable shape. Native-only details such as native
template handles, source maps, and parser-owned trees live inside the selected
engine keyed by `template_id`; they are not extra public fields on a separate
facade class.

Normal assembly APIs consume composable/template handles. They should not need
to copy to CPython AST nodes or lower to source. Artifact extraction is explicit:

```text
composable.to_python_ast_copy()
composable.to_source()
composable.to_executable_ast()
```

Those methods are allowed to allocate and, for lower composables backed by a
native engine, copy from the native AST/IR into CPython `ast`/`_ast` nodes. They
are final-artifact or test paths, not assembly hot paths. Existing tests may use
copied AST nodes and lowered source for parity until structural goldens cover
the new intermediate representation.

Native artifact emitters must fully initialize CPython AST nodes: required
fields, optional/list/context defaults, and source locations must be valid for
the supported Python versions. Constructor deprecation warnings should be
treated as failures in compatibility tests, because those warnings are expected
to harden in newer Python versions.

## Source Locator Scheme

Locators are template-local handles that describe where a record came from and
where materialization should operate. They are not absolute filesystem paths and
they are not Python object reprs.

```text
SourceLocator:
  locator_id
  template_id
  ast_path
  role_key
  parent_locator_id
  authored_summary
  materialization_anchor
```

`ast_path` is a canonical path through the template AST using field and list
segments, such as `body[2].body[1].args`. `role_key` names why the locator
exists, such as `astichi.locator.block_hole`, `astichi.locator.identifier`, or
`astichi.locator.pyimport_prefix`. `materialization_anchor` describes the
operation-level insertion or rewrite anchor needed later.

The exact locator entry shape must be part of the snapshot grammar before
template registration is routed through the lower engine. Template registration
may store richer Python objects internally, but structural snapshots must render
locators through this canonical shape.

## Occurrence State

An occurrence is a template instance in an assembly.

```text
Occurrence:
  occurrence_id
  template_id
  build_path_id
  parent_occurrence_id
  owner_scope_id
  overlay_id
  occurrence_live
```

Adding a composable to a scope creates an occurrence and exposes the live
records derived from its template records. The engine must not clone Python AST
nodes or rebuild Python inventory objects during this step.

Record identity is derived:

```text
RecordId = (occurrence_id, template_record_id)
```

This keeps occurrence creation cheap and avoids rewriting every record when a
template is reused.

Occurrence, edge, and overlay ids are assigned from the ordered engine event
stream: register template, append occurrence, append edge, append overlay. The
Python and native engines must expose deterministic ids for the same ordered calls.
If a native engine reorders internally for performance, that reorder must be
invisible at the snapshot boundary.

## Record State Resolution

Record state has one authoritative query:

```text
record_state(record_id) -> dead | live | satisfied
```

The physical encoding may use an occurrence-live flag, a satisfied-record
bitset, and optional per-record overrides, but candidate lookup, snapshots, and
debug projection must consult `record_state(record_id)` rather than treating
those tables as separate truths.

Resolution order:

1. if the occurrence for the record is not live, the record is `dead`;
2. if the record has a per-record dead override, the record is `dead`;
3. if the record is in the satisfied-record set, the record is `satisfied`;
4. otherwise the record is `live`.

Candidate lookup sees only `live` records. Structural snapshots serialize the
resolved state for each record, not the implementation encoding. This keeps the
Python and native engines free to choose different internal bitsets while still
emitting the same canonical intermediate state.

## Build Paths

Build paths are interned lower-engine objects. They are not repeatedly allocated
as Python tuples on the hot path.

```text
BuildPath:
  build_path_id
  parent_build_path_id
  segment_symbol_id
  depth
```

The Python reference engine can use interned tuples for the first slice, but the
lower API should expose only `BuildPathId` and canonical formatting. A native
engine should use parent-linked build paths with interned path segments. Bit
packing is optional and should be deferred until profiling proves it matters.

## Assembly State

The assembly state owns record-state encoding, indexes, edges, overlays, and
diagnostic journal entries.

```text
AssemblyState:
  occurrences
  record_state_encoding
  indexes
  edges
  overlays
  diagnostic_journal
```

Templates, build paths, and symbols are engine-owned tables. Assembly states
hold handles into those tables. The state may be mutable for a single
`AssemblyScope`. Copy-on-write is needed only when a facade operation must
preserve older state. Copying must copy table/overlay handles, not record
objects.

## Indexes

Candidate lookup must read lower indexes directly.

Required indexes:

```text
by_resource_name: SymbolId -> RecordId list
by_hole_name: SymbolId -> RecordId list
by_identifier_name: SymbolId -> RecordId list
by_external_name: SymbolId -> RecordId list
by_production_name: SymbolId -> RecordId list
by_build_path: BuildPathId -> RecordId list
by_owner_scope: ScopeId -> RecordId list
target_index: TargetKey -> TemplateRecordId list
by_surface: SurfaceId -> RecordId list
```

Index entries point at derived `RecordId` handles. Satisfying a single-add hole
should update `record_state(record_id)` to `satisfied` and let the live filter
hide it from future candidate lookup. It should not require rebuilding every
map.

The first Python implementation can use dictionaries from key to tuple/list of
handles plus `RecordStateEncoding`. A native implementation should use
append-only vectors and compact state bitsets so filtering is branch-cheap.

## Debug Inventory Projection Contract

`scope.inventory` is a compatibility/debug projection over lower state. It is
not the authoritative assembly model and must not run in candidate lookup.

Projection rules:

1. include records whose resolved `record_state(record_id)` is `live`;
2. exclude `satisfied` and `dead` records from the default projection;
3. render overlay state only as debug metadata when the current `Inventory`
   shape can carry it without changing the hot API;
4. preserve existing compatibility expectations for selected fixtures, but use
   structural snapshots for new success-path assertions;
5. order records canonically by rendered build path, source locator, and
   template-record id.

When a full diagnostic snapshot is requested, the structural snapshot may also
include satisfied and dead records with resolved state labels. That richer view
is separate from the projected `Inventory`.

## Edge And Overlay Tables

Composable insertion is represented by an edge:

```text
AssemblyEdge:
  edge_id
  target_record_id
  source_occurrence_id
  order
```

External and identifier bindings are represented as overlays:

```text
Overlay:
  overlay_id
  base_overlay_id
  external_bindings
  identifier_bindings
  keep_names
```

Overlays are immutable lower-engine state. An occurrence owns the overlay that
was current when that occurrence was appended. Applying the same template twice
with different bindings creates two source occurrences with different
`overlay_id` values. Edges point to source occurrences; they do not also carry a
second overlay handle.

The Python facade may store actual external Python objects in an object table
keyed by `ExternalSlotId`, but the lower engine owns the binding graph and
compatibility checks.

## Materialization Plan

Materialization and hygiene belong to the lower layer. The plan is a structural
artifact that can be snapshotted before final Python AST/source output.

```text
MaterializationPlan:
  root_occurrence_id
  operation_stream
  hygiene_stream
  debug_views
  artifact_requests
```

The operation stream is the canonical shape:

```text
MaterializationOperation:
  operation_id
  operation_key
  target_record_id
  source_occurrence_id
  overlay_id
  order
  captures
```

The hygiene stream is canonical lower-engine data:

```text
HygieneOperation:
  operation_id
  operation_key
  target_scope_id
  record_id
  captures
```

`record_id` may be empty for scope-level hygiene decisions such as keep-name
reservations that come from overlay state rather than a single template record.

Debug views may regroup the same streams into inserts, overlays, scope graph,
symbol table, hygiene decisions, and marker gates for readability, but those
sections are projections of `operation_stream` and `hygiene_stream`. They are
not a separate contract.

Plan operations carry both dynamic operation ids and stable operation keys in
snapshots. The Python implementation executes operation classes behind this
stream; the native implementation executes the compact operation stream for
primitives it supports.

Hygiene decisions must not live only in `debug_views`. Python/native parity
compares both the materialization operation stream and the hygiene stream.

The Python lower engine may call existing materialization helpers internally,
but facade code must not reconstruct intent from Python `Inventory` or a legacy
builder graph. If native code is used, it must implement this same contract.

## Python Reference Data Structures

The Python engine should optimize for clarity first, but the public lower API
must be close to the native shape.

Recommended module boundary:

```text
src/astichi/lower_engine/
  __init__.py
  engine.py
  handles.py
  templates.py
  inventory.py
  operations.py
  snapshots.py
  materialization.py
```

Recommended Python structures:

```text
Engine:
  templates: list[Template]
  states: list[AssemblyState]
  symbols: SymbolTable
  build_paths: BuildPathTable
  surface_registry: SurfaceRegistry

AssemblyState:
  occurrences: list[Occurrence]
  edges: list[AssemblyEdge]
  overlays: list[Overlay]
  record_state_encoding: RecordStateEncoding
  indexes: InventoryIndexes
```

Use frozen dataclasses for records that are not mutated after creation. Use
small handle objects or integers consistently; do not expose raw dataclass
instances as the hot API if the native engine cannot match that surface.

Python COW policy:

- mutation within a scope can be in-place;
- snapshots freeze by copying handle lists and sorted indexes;
- facade compatibility projections allocate Python `Inventory` objects only on
  demand;
- no `scope.apply(...)` path should allocate a full projected inventory.

## Python-Only Internal Examples

The examples below are schematic Python lower-engine shapes, not proposed
public constructors. They use semantic object names instead of raw integer
handles where that makes the structure easier to read. Real snapshots should
write stable keys and deterministic text.

Examples render build-path handles with `bp("Root/Child")` for readability.
The real lower API passes `BuildPathId` handles, not raw path strings.

### Example 1: Ordered Block Inserts With Boundary Passes

Authored shape:

```python
root = astichi.compile(
    """
items = []
astichi_hole(body)
result = items
"""
)
first = astichi.compile(
    """
astichi_pass(items, outer_bind=True).append("first")
"""
)
second = astichi.compile(
    """
astichi_pass(items, outer_bind=True).append("second")
"""
)

builder.add.Root(root)
builder.add.First(first)
builder.add.Second(second)
builder.Root.body.add.Second(order=1)
builder.Root.body.add.First(order=0)
```

The facade still exposes three `BasicComposable` objects. Their important
internal fields are the source tree and the semantic inventory extracted at
compile time:

```python
BasicComposable(
    tree="<module: items=[], astichi_hole(body), result=items>",
    markers=("astichi_hole(body)",),
    demand_ports=(BlockHoleDemand("body"),),
    supply_ports=(BlockProductionSupply("__block__"),),
    inventory=Inventory(...),  # debug projection only after registration
)

BasicComposable(
    tree='<module: astichi_pass(items, outer_bind=True).append("first")>',
    markers=("astichi_pass(items, outer_bind=True)",),
    demand_ports=(BoundaryPassDemand("items", outer_bind=True),),
    supply_ports=(BlockProductionSupply("__block__"),),
)
```

The lower engine should register those as templates once:

```python
Template(
    template_id=RootTemplate,
    template_records=[
        TemplateRecord(
            id=RootBodyHole,
            semantic_resource=BlockHoleDemand("body"),
            source_locator="body[1]",
            owner_scope=ModuleScope,
            materialization_role=BlockInsertTarget("body"),
        ),
        TemplateRecord(
            id=RootBlockProduction,
            semantic_resource=BlockProductionSupply("__block__"),
            source_locator=".",
            owner_scope=ModuleScope,
            materialization_role=BlockPayload,
        ),
    ],
    target_index={"body": [RootBodyHole]},
    production_index={"__block__": [RootBlockProduction]},
)

Template(
    template_id=StepTemplate,
    template_records=[
        TemplateRecord(
            id=StepItemsPass,
            semantic_resource=BoundaryPassDemand("items", outer_bind=True),
            source_locator="body[0].value.func.value",
            owner_scope=ModuleScope,
            materialization_role=BoundaryIdentifierUse("items"),
        ),
        TemplateRecord(
            id=StepBlockProduction,
            semantic_resource=BlockProductionSupply("__block__"),
            source_locator=".",
            owner_scope=ModuleScope,
            materialization_role=BlockPayload,
        ),
    ],
    production_index={"__block__": [StepBlockProduction]},
)
```

After `AssemblyScope.add(...)` and two `apply(...)` operations, assembly state
is table state:

```python
AssemblyState(
    occurrences=[
        Occurrence(RootOcc, RootTemplate, build_path=bp("Root")),
        Occurrence(FirstOcc, StepTemplate, build_path=bp("Root/First")),
        Occurrence(SecondOcc, StepTemplate, build_path=bp("Root/Second")),
    ],
    edges=[
        AssemblyEdge(
            target_record=(RootOcc, RootBodyHole),
            source_occurrence=FirstOcc,
            order=0,
        ),
        AssemblyEdge(
            target_record=(RootOcc, RootBodyHole),
            source_occurrence=SecondOcc,
            order=1,
        ),
    ],
    record_state_encoding=RecordStateEncoding(
        live_records={
            (RootOcc, RootBodyHole),
            (RootOcc, RootBlockProduction),
            (FirstOcc, StepItemsPass),
            (FirstOcc, StepBlockProduction),
            (SecondOcc, StepItemsPass),
            (SecondOcc, StepBlockProduction),
        },
    ),
    indexes=InventoryIndexes(
        by_hole_name={"body": [(RootOcc, RootBodyHole)]},
        by_production_name={
            "__block__": [
                (RootOcc, RootBlockProduction),
                (FirstOcc, StepBlockProduction),
                (SecondOcc, StepBlockProduction),
            ],
        },
        by_build_path={
            bp("Root"): [(RootOcc, RootBodyHole), (RootOcc, RootBlockProduction)],
            bp("Root/First"): [(FirstOcc, StepItemsPass), (FirstOcc, StepBlockProduction)],
            bp("Root/Second"): [(SecondOcc, StepItemsPass), (SecondOcc, StepBlockProduction)],
        },
    ),
)
```

Candidate lookup for the two child composables reads `by_hole_name["body"]` and
checks the child template's block production. It does not project a Python
`Inventory`. Materialization later walks `edges` in order and resolves the two
`BoundaryPassDemand("items")` uses against the root scope.

### Example 2: Lifecycle-Shaped Class Template With Params And Overlays

This example is closer to the YIDL lifecycle shape. The root template contains
identifier slots, managed imports, class bases, parameter holes, state
initialization, constructor call arguments, and property inserts:

```python
root = astichi.compile(
    """
astichi_pyimport(module=types, names=(SimpleNamespace,))

class state_name__astichi_arg__:
    __slots__ = (*astichi_hole(state_slots),)

    def __init__(self, state_params__astichi_param_hole__):
        astichi_hole(state_init_body)


class class_name__astichi_arg__(*astichi_hole(class_bases)):
    __slots__ = ("_state",)

    def __init__(self, facade_params__astichi_param_hole__):
        self._state = state_name__astichi_arg__(
            astichi_hole(state_ctor_args)
        )

    astichi_hole(properties)
"""
).bind_identifier(
    class_name="Example",
    state_name="ExampleState",
)
```

The facade object may carry the identifier binding as current metadata, but the
lower engine should store it as an overlay on the root occurrence:

```python
Overlay(
    id=RootOverlay,
    identifier_bindings={
        IdentifierDemand("class_name"): IdentifierValue("Example"),
        IdentifierDemand("state_name"): IdentifierValue("ExampleState"),
    },
    external_bindings={},
    keep_names=frozenset(),
)
```

Template registration captures a larger semantic surface:

```python
Template(
    template_id=LifecycleRootTemplate,
    template_records=[
        TemplateRecord(
            id=TypesImport,
            semantic_resource=ManagedImport(module="types", names=("SimpleNamespace",)),
            source_locator="body[0]",
            owner_scope=ModuleScope,
            materialization_role=ManagedImportPlacement,
        ),
        TemplateRecord(
            id=StateNameIdentifier,
            semantic_resource=IdentifierDemand("state_name"),
            source_locator="body[1].name",
            owner_scope=ModuleScope,
            materialization_role=RewriteIdentifier("state_name"),
        ),
        TemplateRecord(
            id=ClassNameIdentifier,
            semantic_resource=IdentifierDemand("class_name"),
            source_locator="body[2].name",
            owner_scope=ModuleScope,
            materialization_role=RewriteIdentifier("class_name"),
        ),
        TemplateRecord(
            id=ClassBasesHole,
            semantic_resource=ExpressionHoleDemand("class_bases", variadic=True),
            source_locator="body[2].bases[0]",
            owner_scope=ClassScope("class_name"),
            materialization_role=ExpressionInsertTarget("class_bases"),
        ),
        TemplateRecord(
            id=StateSlotsHole,
            semantic_resource=ExpressionHoleDemand("state_slots", variadic=True),
            source_locator="body[1].body[0].value.elts[0]",
            owner_scope=ClassScope("state_name"),
            materialization_role=ExpressionInsertTarget("state_slots"),
        ),
        TemplateRecord(
            id=StateParamsHole,
            semantic_resource=ParameterHoleDemand("state_params"),
            source_locator="body[1].body[1].args",
            owner_scope=FunctionScope("__init__"),
            materialization_role=ParameterInsertTarget("state_params"),
        ),
        TemplateRecord(
            id=FacadeParamsHole,
            semantic_resource=ParameterHoleDemand("facade_params"),
            source_locator="body[2].body[1].args",
            owner_scope=FunctionScope("__init__"),
            materialization_role=ParameterInsertTarget("facade_params"),
        ),
        TemplateRecord(
            id=StateInitBodyHole,
            semantic_resource=BlockHoleDemand("state_init_body"),
            source_locator="body[1].body[1].body[0]",
            owner_scope=FunctionScope("__init__"),
            materialization_role=BlockInsertTarget("state_init_body"),
        ),
        TemplateRecord(
            id=StateCtorArgsHole,
            semantic_resource=FuncargsHoleDemand("state_ctor_args"),
            source_locator="body[2].body[1].body[0].value.args[0]",
            owner_scope=FunctionScope("__init__"),
            materialization_role=FuncargsInsertTarget("state_ctor_args"),
        ),
        TemplateRecord(
            id=PropertiesHole,
            semantic_resource=BlockHoleDemand("properties"),
            source_locator="body[2].body[2]",
            owner_scope=ClassScope("class_name"),
            materialization_role=BlockInsertTarget("properties"),
        ),
    ],
    target_index={
        "class_bases": [ClassBasesHole],
        "state_slots": [StateSlotsHole],
        "state_params": [StateParamsHole],
        "facade_params": [FacadeParamsHole],
        "state_init_body": [StateInitBodyHole],
        "state_ctor_args": [StateCtorArgsHole],
        "properties": [PropertiesHole],
    },
)
```

Child templates expose productions and their own demands. For example, a field
property template is reusable because `field_name` and `storage_path` are
overlay data, not AST rewrites done during candidate application:

```python
Template(
    template_id=PropertyTemplate,
    template_records=[
        TemplateRecord(
            id=FieldNameIdentifier,
            semantic_resource=IdentifierDemand("field_name"),
            source_locator="body[1].name",
            owner_scope=ModuleScope,
            materialization_role=RewriteIdentifier("field_name"),
        ),
        TemplateRecord(
            id=StoragePathExternal,
            semantic_resource=ExternalValueDemand("storage_path"),
            source_locator="body[1].body[0].value.attr",
            owner_scope=FunctionScope("field_name"),
            materialization_role=LowerExternalRef("storage_path"),
        ),
        TemplateRecord(
            id=PropertyBlockProduction,
            semantic_resource=BlockProductionSupply("__block__"),
            source_locator=".",
            owner_scope=ModuleScope,
            materialization_role=BlockPayload,
        ),
    ],
)
```

Two property insertions then become two occurrences with different overlays:

```python
AssemblyState(
    occurrences=[
        Occurrence(RootOcc, LifecycleRootTemplate, bp("Root"), overlay=RootOverlay),
        Occurrence(CountPropOcc, PropertyTemplate, bp("Root/CountProperty"), overlay=CountOverlay),
        Occurrence(LabelPropOcc, PropertyTemplate, bp("Root/LabelProperty"), overlay=LabelOverlay),
    ],
    overlays=[
        Overlay(
            id=CountOverlay,
            identifier_bindings={
                IdentifierDemand("field_name"): IdentifierValue("count"),
            },
            external_bindings={
                ExternalValueDemand("storage_path"): ExternalSlot("_count_current"),
            },
            keep_names=frozenset({"count"}),
        ),
        Overlay(
            id=LabelOverlay,
            identifier_bindings={
                IdentifierDemand("field_name"): IdentifierValue("label"),
            },
            external_bindings={
                ExternalValueDemand("storage_path"): ExternalSlot("_label_value"),
            },
            keep_names=frozenset({"label"}),
        ),
    ],
    edges=[
        AssemblyEdge((RootOcc, PropertiesHole), CountPropOcc, order=0),
        AssemblyEdge((RootOcc, PropertiesHole), LabelPropOcc, order=1),
    ],
)
```

The materialization plan for this example contains more than inserts:

```python
MaterializationPlan(
    root_occurrence=RootOcc,
    operation_stream=[
        Operation(
            key="astichi.operation.splice_params",
            target_record=(RootOcc, StateParamsHole),
            source_occurrence=StateParamsOcc,
            captures={"parameter_region": "state_params"},
        ),
        Operation(
            key="astichi.operation.splice_params",
            target_record=(RootOcc, FacadeParamsHole),
            source_occurrence=FacadeParamsOcc,
            captures={"parameter_region": "facade_params"},
        ),
        Operation(
            key="astichi.operation.splice_body_at_marker",
            target_record=(RootOcc, PropertiesHole),
            source_occurrence=CountPropOcc,
            overlay=CountOverlay,
            order=0,
        ),
        Operation(
            key="astichi.operation.splice_body_at_marker",
            target_record=(RootOcc, PropertiesHole),
            source_occurrence=LabelPropOcc,
            overlay=LabelOverlay,
            order=1,
        ),
        Operation(
            key="astichi.operation.rewrite_identifier",
            target_record=(RootOcc, ClassNameIdentifier),
            overlay=RootOverlay,
            captures={"identifier": "class_name", "value": "Example"},
        ),
        Operation(
            key="astichi.operation.rewrite_identifier",
            target_record=(CountPropOcc, FieldNameIdentifier),
            overlay=CountOverlay,
            captures={"identifier": "field_name", "value": "count"},
        ),
        Operation(
            key="astichi.operation.lower_external_ref",
            target_record=(CountPropOcc, StoragePathExternal),
            overlay=CountOverlay,
            captures={"external": "storage_path", "slot": "_count_current"},
        ),
        Operation(
            key="astichi.operation.gate_no_unresolved",
            captures={
                "identifier_args": True,
                "external_refs": True,
                "insert_targets": True,
            },
        ),
    ],
    hygiene_stream=[
        HygieneOperation(
            key="astichi.operation.keep_name",
            target_scope=ClassScope("Example"),
            record_id=None,
            captures={"name": "count"},
        ),
        HygieneOperation(
            key="astichi.operation.keep_name",
            target_scope=ClassScope("Example"),
            record_id=None,
            captures={"name": "label"},
        ),
        HygieneOperation(
            key="astichi.operation.rename_if_collides",
            target_scope=ClassScope("Example"),
            record_id=None,
            captures={"name": "SimpleNamespace"},
        ),
    ],
    debug_views={},
)
```

This is the important performance property: the same `PropertyTemplate` can be
inserted many times with different overlays. The hot path appends occurrences,
edges, and overlay bindings; it does not clone the property AST or rebuild a
Python `BasicComposable` for each field.

## Lifetime And Ownership

Ownership should be explicit before the native spike, because it determines arena
layout and whether generation counters are needed.

Engine-owned for the engine lifetime:

- surface registry and registered handles;
- template catalog and template source references;
- symbol interner;
- build-path interner;
- operation and pattern descriptor tables.

Assembly-state-owned for the state lifetime:

- occurrences;
- edges;
- overlays;
- record-state encoding;
- lower indexes;
- diagnostic journal.

Facade-owned for the facade scope/build lifetime:

- user-facing `AssemblyScope`;
- external Python object table keyed by `ExternalSlotId`;
- compatibility projections such as `Inventory`;
- final Python AST/source artifacts.

Template ids are valid only for the engine that registered them. Assembly states
reference templates by `TemplateId`; they do not own template copies. External
slots are released when the facade scope/build result that owns them is
released. In v1, template eviction is an engine-level clear-down operation, not
a per-template cache policy.

Required clear-down surface:

```text
engine.close()
state.close()
facade.release_external_slots(state)
```

The exact method names can change, but the ownership split cannot remain
implicit once native tables hold Python object references.

## Native Data Structures

A native engine should own the same logical tables with compact storage. If the
backend is C++, the storage may look like this:

Suggested storage:

```text
Engine:
  std::vector<Template>
  std::vector<AssemblyState>
  StringInterner
  BuildPathArena
  ExternalSlotIdTable

AssemblyState:
  std::vector<Occurrence>
  std::vector<AssemblyEdge>
  std::vector<Overlay>
  std::vector<uint32_t> occurrence_event_order_id
  std::vector<uint32_t> edge_event_order_id
  std::vector<uint32_t> overlay_event_order_id
  RecordStateEncoding
  InventoryIndexes
```

The event-order vectors map native storage indices back to canonical snapshot
ids. They are required if the native engine reorders storage internally while
still exposing deterministic event-order ids at the snapshot boundary.

Template and occurrence ids should be stable vector indices. If deletion is
needed later, use generation counters; do not add generation counters until a
real lifetime case requires them.

Indexes can start with `std::unordered_map<Key, std::vector<RecordId>>`. A
specialized flat map is an optimization gate, not a design dependency.

Record ids can be stored as two 32-bit integers:

```text
struct RecordId {
  uint32_t occurrence;
  uint32_t template_record;
};
```

Native to Python transfer should be bulk-oriented:

- return opaque engine/state handles for normal operations;
- return candidate batches as compact Python tuples or arrays;
- return debug snapshots as canonical dict/list data or bytes;
- never expose one Python wrapper object per lower record on the hot path.

## Python Boundary Ownership

The facade owns:

- user-facing `AssemblyScope`;
- current YIDL adapter functions;
- actual Python external objects;
- conversion from lower artifacts to `BasicComposable`, `ast.Module`, source,
  and debug output.

The lower engine owns:

- template metadata;
- occurrence and inventory state;
- candidate lookup;
- inventory merge;
- overlays;
- materialization plan construction;
- hygiene decisions;
- structural snapshots.

The facade must not be required to iterate record by record to complete a normal
assembly operation.
