# Inventory API

`BasicComposable.inventory` is the immutable inventory of bindable Astichi
resources discovered for that composable. It is lower level than
`Composable.describe()`: descriptor objects are the public planning surface,
while inventory records are the map-backed source used to discover bindable
points cheaply.

Inventory includes bindable resources only:

- additive holes
- parameter holes
- identifier demands and supplies
- external binds

Comment markers and keep directives are not bindable and do not appear in the
inventory maps.

## Records And Maps

`Inventory.records` is the authoritative map from `InventoryRecordId` to
`InventoryRecord`. Compile-time records use IDs such as `#1` and `#2`. Builder
merge records prefix those IDs with their build path, such as `Root/#1` or
`Root/Step/#1`.

Lookup maps store record IDs, not full records:

| Map | Meaning |
| --- | --- |
| `resource_map` | Every bindable resource by logical name. |
| `port_map` | Port-like bindables by logical port name. |
| `hole_map` | Additive and parameter holes by logical name. |
| `identifier_map` | Identifier demands and supplies by logical name. |

Use the accessors when possible:

```python
ids = composable.inventory.hole_record_ids("body")
records = composable.inventory.records_for_ids(ids)
```

`find_resource(...)` filters by logical name, kind, build path, and code owner
when a caller needs more than a single map lookup.

## Pretty Print

`str(inventory)` and `repr(inventory)` return the same stable snapshot. The
`records:` section always prints, even when empty. Non-empty maps print one
logical name per line with record IDs listed inline.

Example:

```text
records:
  #1 build_path=. code_owner=. name=body kind=hole.block locator=body[0]/value

resource_map:
  body: #1

port_map:
  body: #1

hole_map:
  body: #1
```

This format is intended for diagnostics and focused tests; it is not a
serialized interchange format.

## Descriptor Relationship

`Composable.describe()` projects its holes, external binds, and identifier
descriptors from immutable inventory records. Production descriptors still use
the existing body/payload checks because they describe what the composable can
contribute, not a bindable point.
