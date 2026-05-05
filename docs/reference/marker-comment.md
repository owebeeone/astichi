# Marker: `astichi_comment`

`astichi_comment("...")` carries generated-comment intent through Astichi's
AST-based composition pipeline. It is useful when final source should explain
where generated code came from or why a generated block is intentionally empty.

The marker is valid Python syntax while Astichi is composing, but it is not a
runtime helper.

## Authored Form

```python
astichi_comment("generated from {__file__}:{__line__}")
astichi_comment("line one\nline two")
```

Rules:

- the marker must be a standalone statement
- it accepts exactly one positional argument
- the argument must be a literal `str`
- keyword arguments, f-strings, variables, and string expressions reject

Invalid forms:

```python
value = astichi_comment("no value")
return astichi_comment("no value")
astichi_comment(text="no kwargs")
astichi_comment(prefix + suffix)
astichi_comment(f"{name}")
```

## Emission Modes

Ordinary `emit()` preserves `astichi_comment(...)` calls so marker-bearing
source can round-trip through `emit()` -> `compile(...)`.

Executable `materialize()` strips comment markers. If stripping leaves a
non-module Python suite empty, Astichi inserts `pass` so the result remains
valid Python:

```python
if enabled:
    astichi_comment("nothing to do\nhere")
```

Executable materialized output:

```python
if enabled:
    pass
```

Use `emit_commented()` when final inspectable source should contain real Python
comments:

```python
if enabled:
    # nothing to do
    # here
    pass
```

`emit_commented()` is a peer operation to `materialize()`, not a mode of
ordinary `emit()`. It returns plain source and does not accept `provenance=`.

## Source-Location Placeholders

Comment payloads replace only these exact substrings:

- `{__file__}`: the logical source filename from the marker's origin
- `{__line__}`: the 1-based AST source line of the marker

Every occurrence of those exact substrings is replaced. Other brace-delimited
text passes through unchanged:

```python
astichi_comment("{__file__}:{__line__} kept literally: {field_name}")
```

If the snippet was compiled with `file_name="schema/projector.py"` and the
marker is on line 17, `emit_commented()` renders:

```python
# schema/projector.py:17 kept literally: {field_name}
```

Pass stable logical or repo-relative filenames to `compile(...)` when the
rendered output is committed or compared in tests. Astichi does not invent
machine-specific paths for comment rendering.

## Indentation

Multi-line payloads render each line at the indentation of the marker statement:

```python
if enabled:
    astichi_comment("nothing to do\nhere")
```

renders as:

```python
if enabled:
    # nothing to do
    # here
    pass
```

## Reference Snippet

- [comment/generated_comment](snippets/comment/generated_comment/recipe.py)

## See Also

- [Materialize and emit](materialize-and-emit.md)
- [Composable API](composable-api.md)
- [Marker overview](marker-overview.md)
