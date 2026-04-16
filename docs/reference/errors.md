# Errors

Hard errors the implementation raises when rules are violated. Exception
types and messages are part of the **stable user contract** for each release;
categories below follow **[§15](../../dev-docs/AstichiApiDesignV1.md)**.

| Situation | Typical outcome |
|-----------|-----------------|
| Invalid marker placement | Error at compile / lowering |
| Unsupported `*` / `**` marker context | Error (fail early) |
| Invalid `astichi_keep(...)` argument (not bare identifier) | Error |
| Unresolved free identifier in **strict** mode | Error |
| Same variadic target, same `order` on two inserts | Error |
| `astichi_for` target unpacking fails at compile time | Error |
| Provenance restore on edited / non-matching source | Error; remove `astichi_provenance_payload(...)` |

For **`SyntaxError`** from `compile`, see [compile-api.md](compile-api.md).
