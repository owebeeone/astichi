# Lower Template Package V2

Status: proposed contract update for the native lower-engine roll build.

The current structural inventory snapshot is behavior-incomplete. It captures
template records, locators, occurrences, edges, overlays, and materialization
plan projections, but Python materialization still reaches back into
`BasicComposable.markers`, name classification, and source AST walks for
managed imports and hygiene.

That side channel is the design issue. If data affects candidate selection,
materialization, hygiene, diagnostics, or final artifact output, it belongs in
the lower-engine contract. Private/native metadata is allowed only for caches
and indexes derived from that contract.

## Contract Boundary

`LowerTemplatePackageV2` is the canonical template payload consumed by both the
Python lower engine and the native lower engine.

```text
LowerTemplatePackageV2:
  schema
  surface_bundle_signature
  template_key
  source_summary
  string_table
  path_table
  ast_path_table
  locators
  records
  scopes
  markers
  managed_imports
```

The package is the runtime contract. Structural JSON goldens are readable
projections of the same package, not the hot-path representation.

During the Python migration, schema pieces may land in staged slices. The final
v2 package includes all tables shown above. Early Python slices may populate
only locators, records, scopes, and binding sets; marker and managed-import
tables land when their extractor slices begin. Staged package snapshots should
omit not-yet-implemented tables rather than locking empty sections into early
goldens. The final v2 snapshot includes the complete table set.

## Encoding Goals

- Serialize and deserialize without nested Python object graphs.
- Let hot paths operate on integer ids, flags, and row indexes.
- Keep all behavior-affecting data canonical and golden-testable.
- Keep arbitrary maps out of runtime rows; debug snapshots may expand rows into
  named objects.
- Keep native-private indexes strictly derived from package rows.

## Interning Policy

Interning is package-local in v1:

- string, path, and AST-path ids are assigned in deterministic extraction order;
- ids are valid only inside one package;
- no inter-package id reuse is permitted in v1;
- debug/golden snapshots render strings and paths, not raw intern ids;
- canonical comparisons must not depend on intern id values except for row-local
  references that are resolved by the snapshot renderer.

This trades some per-template allocation for trivial teardown and avoids
long-running host lifetime questions until the schema is stable.

## Tables

### String Table

All stable strings are interned:

```text
StringTable:
  strings: Vec<String>
```

Interned values include surface keys, operation keys, inventory kinds, role
keys, resource names, owner path parts, binding names, module path parts, and
source marker names.

### Path Tables

Owner paths, build paths, module paths, and AST paths should be encoded once and
referenced by id.

```text
PathTable:
  paths: Vec<Vec<StringId>>

AstPathTable:
  paths: Vec<Vec<AstPathSegment>>

AstPathSegment:
  field_id: StringId
  index: u32 | none
```

The debug snapshot may still render AST paths as strings such as
`body[0]/value`. Hot paths should use segment vectors.

### Locators

```text
LocatorRow:
  locator_id: u32
  ast_path_id: AstPathId
  role_key_id: StringId
  parent_locator_id: LocatorId | none
  authored_summary_id: StringId
  materialization_anchor_id: StringId
```

### Records

```text
RecordRow:
  template_record_id: u32
  surface_id: u32
  operation_id: u32
  locator_id: LocatorId
  resource_name_id: StringId | none
  inventory_kind_id: StringId
  owner_path_id: PathId
  semantic_summary_id: StringId
  flags: RecordFlags
```

The current record/locator snapshot is a readable projection of these rows.

### Scopes

Scopes replace the current Python-only name-classification side channel.

```text
ScopeRow:
  scope_id: u32
  parent_scope_id: ScopeId | none
  scope_kind: module | function | async_function | class
  ast_path_id: AstPathId
  owner_path_id: PathId
  local_binding_set_id: StringSetId
  argument_set_id: StringSetId
```

`local_binding_set_id` includes names bound by assignment, delete targets,
function/class definitions, imports, and other scope-local binders. Function
arguments are also recorded separately because some hygiene rules need to know
the source of the binding.

### Markers

Markers are canonical lower-engine data, including marker-only syntax that does
not produce an inventory record.

```text
MarkerRow:
  marker_id: u32
  source_order: u32
  marker_kind: keep | import | export | pass | pyimport | comment | ref | unroll
  operation_id: u32
  scope_id: ScopeId
  owner_path_id: PathId
  ast_path_id: AstPathId
  statement_path_id: AstPathId | none
  resource_name_id: StringId | none
  flags: MarkerFlags
```

Initial marker flags:

```text
explicit_bind_enabled
outer_bind_enabled
is_statement_marker
is_metadata_marker
```

Marker captures that affect behavior should be represented by typed columns or
side tables, not by arbitrary maps. Debug projections may render captures as a
dictionary.

### Managed Imports

Managed imports are normalized from pyimport markers because materialization
wants this shape directly.

```text
ManagedImportRow:
  managed_import_id: u32
  marker_id: MarkerId
  source_order: u32
  scope_id: ScopeId
  module_path_id: PathId
  final_local_name_id: StringId
  original_symbol_id: StringId | none
  flags: ManagedImportFlags
```

Initial managed import flags:

```text
from_import
plain_import
```

## Derived Indexes

The following are caches, not contract data:

```text
records_by_inventory_kind
records_by_resource_name
records_by_owner
markers_by_scope
markers_by_kind
markers_by_occurrence
managed_imports_by_scope
bindings_by_scope
locators_by_ast_path
```

Python may build them as dictionaries over row ids. Native should build them as
vectors, sorted row ranges, or compact hash maps. They are disposable and must
be rebuildable from the package.

## Runtime And Golden Forms

Runtime representation:

- Python reference: dataclasses or small typed containers over primitive lists.
- Native: vectors of primitive row structs plus derived indexes.
- Future binary transport: MessagePack/CBOR-like or a simple custom binary
  format, but only after the schema is stable.

Golden representation:

- canonical JSON projection of the package;
- stable keys and rendered strings for reviewability;
- no memory addresses, absolute paths, object reprs, or runtime handles.

## API Shape

The lower-engine API should move from snapshot-oriented registration to package
registration.

```text
extract_lower_template_package(source, origin, surface_bundle) -> LowerTemplatePackageV2
register_template_package(engine, package) -> TemplateHandle
template_package_snapshot(template) -> canonical JSON projection
build_materialization_plan(package_store, assembly_state) -> MaterializationPlan
```

The current structural snapshot APIs remain debug/golden projections:

```text
structural_snapshot(state, materialization_plan) -> StructuralSnapshot
```

## Python-First Migration

The detailed Python roll-build slices are in
`dev-docs/perf-refactor/PythonLowerTemplatePackageV2Plan.md`.

1. Add Python `LowerTemplatePackageV2` containers populated from existing
   `BasicComposable.markers`, name classification, inventory extraction, and
   compile source metadata.
2. Extend goldens to compare package projections for representative templates.
3. Refactor Python materialization planning to use package/state APIs only,
   removing reads from `AssemblyScope._lower_composable_by_occurrence` for
   hygiene-plan construction.
4. Teach native extraction to produce the same package rows from native parser
   data.
5. Route native N9b3 hygiene streams through package rows and derived indexes.

## Acceptance Rules

- Any behavior-affecting fact must be present in the package or derivable from
  package rows and assembly state.
- Private engine metadata may only cache or index package/state facts.
- Python and native package snapshots must match for the same source and
  surface bundle.
- Materialization-plan goldens must be generated from package/state APIs, not
  Python composable side channels.
