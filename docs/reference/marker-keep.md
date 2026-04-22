# Marker: `astichi_keep`

## Form

```python
astichi_keep(name)
```

`name` must be a **bare identifier** (e.g. `astichi_keep(sys)` — `sys` is the
identifier passed to the marker).

## Semantics

- **Preserves** that identifier’s spelling through composition / hygiene passes.
- The name is **not** renamed to avoid capture; generated locals must **not**
  collide with it.
- This is a **lexical preservation** rule for composition, **not** a guarantee of
  Python import or scope semantics by itself.

## Classification

Keep-marker recognition runs **before** ordinary free-name classification on the
same subtree (V1 §6).

## See also

- [scoping-hygiene.md](scoping-hygiene.md)
- [classification-modes.md](classification-modes.md)
- **[§5.5](../../dev-docs/AstichiApiDesignV1.md)**
