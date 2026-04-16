# Compile API

## Signature

```python
def compile(
    source: str,
    file_name: str | None = None,
    line_number: int = 1,
    offset: int = 0,
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

The compiler prepends blank lines and spaces before calling **`ast.parse`**, so
`lineno` / `col_offset` on the parsed `ast` align with the host file.

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
