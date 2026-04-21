# Compile API

## Signature

```python
def compile(
    source: str,
    file_name: str | None = None,
    line_number: int = 1,
    offset: int = 0,
    *,
    arg_names: Mapping[str, str] | None = None,
    keep_names: Iterable[str] | None = None,
    source_kind: Literal["authored", "astichi-emitted"] = "authored",
) -> Composable: ...
```

Exposed as **`astichi.compile`** and **`astichi.frontend.compile`**.

## Parameters

| Parameter | Default | Role |
|-----------|---------|------|
| `source` | (required) | Python source text using **Astichi markers** where needed. |
| `file_name` | `"<astichi>"` | Logical filename attached to `SyntaxError` and parse results. |
| `line_number` | `1` | 1-based line in the **original container** where the first line of `source` begins. |
| `offset` | `0` | Leading spaces prepended so the first character’s **column** matches the original slice. |
| `arg_names` | `None` | Initial identifier resolutions for `__astichi_arg__`, `astichi_import`, or `astichi_pass` demand names. Equivalent to calling `.bind_identifier(...)` on the returned composable, but validated during compile. |
| `keep_names` | `None` | Identifier names to preserve through hygiene, additive with authored `astichi_keep(...)` / `__astichi_keep__` sites. |
| `source_kind` | `"authored"` | `"authored"` is the normal user-snippet mode. `"astichi-emitted"` is only for re-ingesting Astichi-emitted source that contains internal metadata such as `astichi_insert(...)`. |

The compiler prepends blank lines and spaces before calling **`ast.parse`**, so
`lineno` / `col_offset` on the parsed `ast` align with the host file.

`source_kind="authored"` rejects internal `astichi_insert(...)` metadata. Use
`astichi_hole(...)` plus `astichi.build()` to compose authored snippets.

## Result

Returns a **`Composable`** produced by the lowering pipeline:

1. Parse Python AST  
2. Recognize markers  
3. Classify names (strict / permissive, preserved names, externals)  
4. Lower into the internal composable model  

See **[§7](../../dev-docs/AstichiApiDesignV1.md)** in the design doc.

The value retains **origin** metadata (`CompileOrigin`: file, line, offset) for
diagnostics and provenance.

## Errors

Invalid Python raises **`SyntaxError`** with **`filename`** and **`lineno`**
consistent with `file_name` and padded positions.

Marker or lowering violations raise **Astichi** diagnostics (exact exception
types are part of the public API contract for the release).

## See also

- [Composable API](composable-api.md)
- [Classification modes](classification-modes.md)
- **[§4 — Compile API](../../dev-docs/AstichiApiDesignV1.md)**
