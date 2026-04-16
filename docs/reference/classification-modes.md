# Name classification modes

Astichi classifies identifiers in snippets before lowering. **Lexical hygiene**
must follow
**[`IdentifierHygieneRequirements.md`](../../dev-docs/IdentifierHygieneRequirements.md)**.

## Name classes

- Local / generated bindings
- Explicit **`astichi_keep`**
- Explicit **`astichi_bind_external`**
- Unresolved **free** identifiers

Context may supply **`preserved_names`** (ambient roots like `print`, `sys`) and
**`external_values`** (compile-time map for externals).

## Strict mode

Unresolved frees → **error**, unless kept, declared external, or in the
preserved-name set.

## Permissive mode

Unresolved frees may become **implied named demands**.

## Classification order

1. Collect locals  
2. Collect explicit `astichi_keep`  
3. Merge context preserved names  
4. Collect explicit externals  
5. Classify remaining frees (per mode)

Local colliding with a preserved name: **strict** → error; **permissive** →
hygiene-rename the **local** and its references.

## See also

- [marker-keep.md](marker-keep.md)
- **[§6](../../dev-docs/AstichiApiDesignV1.md)**
