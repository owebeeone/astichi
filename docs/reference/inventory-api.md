# Inventory API

`BasicComposable.inventory` is the immutable inventory of Astichi resources
discovered for that composable. It is lower level than `Composable.describe()`:
descriptor objects are the public planning surface, while inventory records are
the map-backed source used to discover bindable points and production surfaces
cheaply.

Inventory includes resources that a builder, descriptor adapter, or assembler
needs to discover without rescanning the AST:

- additive holes
- parameter holes
- identifier demands and supplies
- external binds
- production surfaces such as `__block__`, `__expr__`, and `__funcargs__`

Comment markers and keep directives are not bindable or producible resources
and do not appear in the inventory maps.

## Records And Maps

`Inventory.records` is the authoritative map from `InventoryRecordId` to
`InventoryRecord`. Compile-time records use IDs such as `#1` and `#2`. Builder
merge records prefix those IDs with their build path, such as `Root/#1` or
`Root/Step/#1`.

Lookup maps store record IDs, not full records:

| Map | Meaning |
| --- | --- |
| `resource_map` | Every discovered resource by logical name, including productions. |
| `port_map` | Port-like resources by logical port name, including production ports. |
| `hole_map` | Additive and parameter holes by logical name. |
| `identifier_map` | Identifier demands and supplies by logical name. |
| `production_map` | Production surfaces by logical production name. |

Use the accessors when possible:

```python
ids = composable.inventory.hole_record_ids("body")
records = composable.inventory.records_for_ids(ids)
production_ids = composable.inventory.production_record_ids("__block__")
```

`find_resource(...)` filters by logical name, kind, build path, and code owner
when a caller needs more than a single map lookup.

Each `InventoryRecord` carries the split identity needed by staged builds:

- `build_path`: builder identity such as `Root` or `Root/Step`
- `code_owner`: logical Python owner path such as `GeneratedClass/run`
- `name`: logical Astichi name, with suffixes such as `__astichi_arg__` stripped
- `kind`: boundary string such as `hole.block`, `external.bind`, or
  `production.block`
- `locator`: structural path back to the AST node
- `payload`: semantic data used by descriptor reconstruction and compatibility
- `source_location`: optional logical source file and line for diagnostics

Build path and code owner are intentionally separate. Binding
`class_name__astichi_arg__` changes Python code identity; adding that same
composable under `Root/Step` changes builder identity.

## Pretty Print

`str(inventory)` and `repr(inventory)` return the same stable snapshot. The
`records:` section always prints, even when empty. Non-empty maps print one
logical name per line with record IDs listed inline.

Example:

```text
records:
  #1 build_path=. code_owner=. name=body kind=hole.block locator=body[0]/value
  #2 build_path=. code_owner=. name=__block__ kind=production.block locator=.

resource_map:
  __block__: #2
  body: #1

port_map:
  __block__: #2
  body: #1

hole_map:
  body: #1

production_map:
  __block__: #2
```

This format is intended for diagnostics and focused tests; it is not a
serialized interchange format.

## Descriptor Relationship

`Composable.describe()` is a wrapper over immutable inventory records. It
projects holes, aggregate ports, external binds, identifier descriptors, and
production descriptors from the inventory and its maps. AST inspection happens
when inventory is constructed or rebuilt, not during `describe()`.

Production records describe what the composable can contribute to a future
builder stage. Composable-surface productions use build path `.`, while
occurrence resources inside built composables use concrete build paths such as
`Root/Step`.
