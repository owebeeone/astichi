# Errors

Hard errors the implementation raises when rules are violated. Exception
types and messages are part of the **stable user contract** for each release;
categories below follow **[§15](../../dev-docs/historical/AstichiApiDesignV1.md)**.

| Situation | Typical outcome |
|-----------|-----------------|
| Invalid marker placement | Error at compile / lowering |
| Reserved / obsolete marker name such as `astichi_bind_once(...)` or `astichi_bind_shared(...)` | Error at compile / lowering |
| Unsupported `*` / `**` marker context | Error (fail early) |
| Invalid parameter-hole marker placement or malformed `astichi_params` payload | Error at compile / lowering |
| Parameter payload wired into a non-parameter target, or non-parameter payload wired into a parameter target | Error at build |
| Duplicate final parameter names, duplicate inserted `*args`, or duplicate inserted `**kwargs` | Error at materialize |
| Unresolved required default hole or overfilled optional annotation hole in a parameter payload | Error at build / materialize |
| Invalid `astichi_keep(...)` argument (not bare identifier) | Error |
| Unresolved free identifier in **strict** mode | Error |
| Same variadic target, same `order` on two inserts | Error |
| `astichi_for` target unpacking fails at compile time | Error |
| Provenance restore on edited / non-matching source | Error; remove the trailing `# astichi-provenance: ...` comment |

For **`SyntaxError`** from `compile`, see [compile-api.md](compile-api.md).
