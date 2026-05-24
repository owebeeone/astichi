# Structural Snapshot Grammar

Status: draft mini-spec.

This is the Slice 2 snapshot grammar target. It is intentionally small, but it
must be concrete enough that the writer and reader can round-trip hand-built
lower-engine state before production code routes through the lower engine.

## Canonical Sections

```text
schema
surface_bundle
templates
locators
occurrences
records
edges
overlays
materialization
diagnostics
```

All maps are written in sorted key order. Lists are written in deterministic
engine event order unless a section defines a more specific order. Snapshots
must not contain absolute paths, Python object reprs, process ids, memory
addresses, or hash-order-dependent output.

## Identity Rules

Dynamic `SurfaceId`, `PatternId`, and `OperationId` values are not canonical
snapshot identities. Snapshots write stable keys and schema versions for those
concepts.

Occurrence, edge, overlay, template, and record ids are canonical only because
both engines assign them from the same ordered event stream. If an engine
optimizes internal ordering, the snapshot boundary must still expose the
canonical event-order ids.

For JSON snapshots, ids are encoded as:

- `template_id`, `occurrence_id`, `edge_id`, `overlay_id`, and `locator_id`:
  non-negative integers;
- `record_id`: two-element array `[occurrence_id, template_record_id]`.

Other encodings, such as packed integers or `"occurrence:record"` strings, may
exist internally but are not the v1 snapshot wire format.

## Schema Versioning

`astichi.structural-inventory.v1` is the only supported schema in this design
slice. Readers reject any other schema with `SchemaMismatchError`. Forward
compatibility is not provided in v1; readers do not silently tolerate unknown
top-level sections or unknown required fields.

## Record Shape

```text
record:
  record_id
  occurrence_id
  template_record_id
  surface_key
  semantic_summary
  locator_id
  state
```

`state` is the resolved value from `record_state(record_id)`. The snapshot does
not expose the internal state bitset layout.

## Locator Shape

```text
locator:
  locator_id
  template_id
  ast_path
  role_key
  parent_locator_id
  authored_summary
  materialization_anchor
```

`ast_path` is relative to the template AST, for example
`body[2].body[1].args`.

## Materialization Shape

```text
materialization:
  root_occurrence_id
  operation_stream:
    - operation_key
      target_record_id
      source_occurrence_id
      overlay_id
      order
      captures
  hygiene_stream:
    - operation_key
      target_scope_id
      record_id
      captures
  debug_views
  artifact_requests
```

`debug_views` may regroup the streams for readability, but `operation_stream`
and `hygiene_stream` are the contracts used for Python/native parity.

In `hygiene_stream`, `record_id` is either a two-element record id array or
`null` for scope-level decisions not owned by one template record.

## Round Trip

The first implementation only needs to prove:

```text
state -> snapshot -> text -> snapshot -> text
```

with identical final text. Later slices add structural goldens from real
assembly fixtures.
