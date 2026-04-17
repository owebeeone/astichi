# Astichi API design V1: marker-preserving emission

This document defines the V2-era surface for marker-preserving emission —
emitting valid Python source for an un-materialized composable so that
unresolved markers (holes, external binds) remain as visible, re-parseable
call sites.

It resolves the deferred item `V1DeferredFeatures.md §3.1`.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md` (normative base design)
- `astichi/dev-docs/AstichiApiDesignV1-InsertExpression.md` (§§9–12
  on expression inserts; still apply)
- `astichi/dev-docs/AstichiApiDesignV1-BindExternal.md` (unresolved
  binds also survive into skeleton output)
- `astichi/dev-docs/AstichiApiDesignV1-UnrollRevision.md` (skeleton
  output may contain un-unrolled `astichi_for` loops)
- `astichi/dev-docs/V2Plan.md` (Phase 3f)

## 1. Problem statement

Today, the only supported emission path requires `materialize()`:

```text
compile → build → materialize → emit   (strict, closed)
```

`materialize()` rejects any unresolved `astichi_hole` demand or (V2)
unresolved `astichi_bind_external` demand. This is correct as a
**release** gate but is hostile to:

- **Partial authoring workflows** — iterating on a composable and
  wanting to see what it looks like before it is closed.
- **Tooling** — diff-friendly intermediate artifacts, caching,
  debugging dumps.
- **Round-trip editing** — emit partial source, edit it by hand (or
  another tool), re-parse, keep composing.

A second supported path with the same textual output discipline but
without the unresolved-demand gate fills this gap.

## 2. Canonical example

```python
source_a = """
class Subject:
    astichi_hole(class_body)
"""

source_b = """
@astichi_insert(class_body)
def method_a(self):
    return 1

@astichi_insert(class_body)
def method_b(self):
    astichi_hole(body)
"""

builder = astichi.build()
builder.add.Shell(astichi.compile(source_a))
builder.add.Piece(astichi.compile(source_b))
builder.Shell.class_body.add.Piece()

partial = builder.build()  # not materialized
skeleton = partial.emit(mode="markers")
```

Expected `skeleton` output:

```python
class Subject:

    def method_a(self):
        return 1

    def method_b(self):
        astichi_hole(body)
```

The `body` hole remains as a plain call expression — valid Python and
a valid Astichi marker. Re-parsing the skeleton through
`astichi.compile(skeleton)` produces a fresh composable with the
`body` demand still open.

## 3. Key invariants

### 3.1 Skeleton is valid Python

All Astichi markers are structural Python function calls or decorators.
Nothing in marker-preserving emission invents new syntax; the text
always parses with the stock Python parser.

### 3.2 Skeleton re-parses into a fresh composable

`astichi.compile(composable.emit(mode="markers"))` must succeed and
produce a composable whose marker set matches the source composable's
**remaining** markers (the ones that were still open in the skeleton).

### 3.3 Hygiene is still applied

Skeleton emission runs the hygiene closure (scope identity + collision
rename) before unparsing. Without this, a partial tree can end up with
name collisions that would appear in the skeleton text and complicate
downstream editing. Hygiene is the only transformation applied; nothing
else is eagerly resolved.

### 3.4 Markers are preserved structurally

`astichi_hole(name)`, `astichi_bind_external(name)`,
`@astichi_insert(target)` (both decorator and call-expression forms),
`astichi_keep(name)`, `astichi_export(name)`, and `astichi_for(domain)`
all survive unchanged if they are unresolved at skeleton time.

### 3.5 Strict mode is unchanged

`emit(mode="strict")` (default) keeps the V1 contract: requires the
composable to have been materialized; fails loudly otherwise.

## 4. API surface

```python
class BasicComposable:
    def emit(
        self,
        *,
        mode: Literal["strict", "markers"] = "strict",
        provenance: bool = True,
    ) -> str: ...
```

Behavior by mode:

| Mode | Requires materialized? | Unresolved markers | Hygiene | Provenance |
|------|------------------------|--------------------|---------|------------|
| `"strict"` | yes (default today) | error | already done | yes (default) |
| `"markers"` | no | preserved | applied here | yes (default) |

`mode="strict"` raises a clear error when called on a non-materialized
composable (unresolved demand ports exist). `mode="markers"` accepts
both materialized and non-materialized composables — if every demand is
resolved, the output is identical to strict mode.

## 5. Pipeline placement

Strict:

```text
compile → build → materialize → emit(strict) → source
```

Markers:

```text
compile → build → emit(markers) → skeleton-source
```

Internally, `emit(mode="markers")` performs:

1. Deep-copy the composable's tree.
2. Apply hygiene closure (`assign_scope_identity`,
   `rename_scope_collisions`) — the same closure that `materialize()`
   runs.
3. Re-extract markers and ports on the mutated tree.
4. `emit_source(tree, provenance=provenance)` — same code path as
   strict mode.

The only difference vs `materialize()` is step **0**: skip the
mandatory-demand gate (unresolved holes, unresolved bind-externals).

## 6. Factoring in the codebase

To keep both modes on a single shared path, the hygiene-closure part
of `materialize_composable` factors out:

```python
# src/astichi/materialize/api.py

def close_hygiene(composable: BasicComposable) -> BasicComposable:
    """Apply hygiene closure; do not enforce demand-resolution gate."""
    ...

def materialize_composable(composable: BasicComposable) -> BasicComposable:
    """Validate completeness and apply final hygiene."""
    _enforce_demand_gate(composable)  # strict-only step
    return close_hygiene(composable)
```

`close_hygiene` is reused by:

- `materialize_composable` (strict path, after the gate).
- `BasicComposable.emit(mode="markers")` (markers path, no gate).

No duplicated hygiene logic.

## 7. Provenance

The provenance comment embeds the pickled AST of what was emitted.
For `mode="markers"`, the payload is the hygiene-closed, marker-preserving
tree. Round-trip verification (`verify_round_trip`) still applies:

```python
skeleton = composable.emit(mode="markers")
verify_round_trip(skeleton)  # succeeds
```

Re-reading the provenance payload yields the exact tree that was
unparsed, including the preserved marker nodes.

## 8. Round-trip semantics

Given:

```python
s0 = composable.emit(mode="markers")
c1 = astichi.compile(s0)
s1 = c1.emit(mode="markers")
```

Expectation: `s1 == s0` **after** both have been hygiene-closed (which
is automatic in `emit(mode="markers")`). This gives the skeleton a
stable textual fixed point — tooling can rely on it.

Caveat: if the source composable was materialized before the first
skeleton emission (so all markers were resolved), there is nothing to
preserve and the output equals strict-mode output. That also
round-trips cleanly.

## 9. Interaction with bind + unroll

V2 adds two new marker families worth naming explicitly:

- **Unresolved `astichi_bind_external(name)`** survives into skeleton
  output as a statement. A later `astichi.compile(skeleton).bind(name=...)`
  pass satisfies it.
- **Un-unrolled `astichi_for` loops** survive as `for ... in
  astichi_for(domain):` loops with the original domain expression
  preserved. A later `build(unroll=True)` unrolls them.

No new logic is required for these — they are valid Python call
expressions already.

## 10. Errors

At `emit(mode="markers")` time:

- **`ValueError`** if hygiene closure itself fails (e.g. an internal
  invariant bug). The error mentions hygiene, not materialize.
- No errors about unresolved demands — that is the whole point.

At `emit(mode="strict")` time, when called on a non-materialized
composable:

- **`ValueError`**: "strict emission requires a materialized composable;
  call `.materialize()` first or use `emit(mode='markers')`." Names the
  first unresolved demand for quick diagnosis.

## 11. Non-goals for V2

Out of scope in this addendum:

- **Pretty-printing configuration** — still driven entirely by
  `ast.unparse`. Format negotiation is a separate deferred item.
- **Skeleton-mode emission of partially unrolled trees** — either a
  loop is unrolled (then no marker to preserve) or it is not (then
  the for-loop text survives). No half-unrolled skeleton.
- **Diff / patch generation** between two skeletons — downstream
  tooling concern, not an emission mode.

## 12. Implementation outline

1. **Factor `close_hygiene` out of `materialize_composable`** in
   `src/astichi/materialize/api.py`.
2. **Extend `emit_source` / `emit()`** to accept `mode` parameter.
   `src/astichi/emit/api.py` gets a new `mode` argument passed through
   to `BasicComposable.emit`.
3. **Update `BasicComposable.emit`** in `src/astichi/model/basic.py`
   to route:
   - `mode="strict"` → `emit_source(close_hygiene(self).tree, ...)`
     only if materialized; raise otherwise.
   - `mode="markers"` → `emit_source(close_hygiene(self).tree, ...)`.
4. **Tests** (extend `tests/test_emit.py` and/or new
   `tests/test_marker_preserving_emit.py`):
   - Skeleton output preserves unresolved holes.
   - Skeleton output preserves unresolved bind-externals.
   - Skeleton output preserves un-unrolled `astichi_for` loops.
   - Skeleton re-parses into a fresh composable with matching markers.
   - Textual fixed point: `emit(markers) → compile → emit(markers)`
     is idempotent after the first emission.
   - Hygiene applied: collisions renamed in skeleton output.
   - `emit(strict)` on a non-materialized composable raises with a
     clear error that mentions `emit(mode="markers")` as an alternative.
   - `emit(strict)` on a materialized composable is byte-identical to
     its pre-V2 behavior (regression test).
   - Provenance round-trip succeeds for skeleton output.

## 13. Open questions

### 13.1 Should `build()` return a composable that auto-marks itself as "not materialized"?

V1 already distinguishes by way of the "did materialize run" state.
Current code path: `BasicComposable` does not carry this bit
explicitly; materialize returns a new composable and the caller tracks
state. V2 skeleton emission does not require this bit either — it
simply always runs hygiene closure.

**Recommendation**: no new state bit; keep `BasicComposable` carrying
only the tree + caches.

### 13.2 Should skeleton output elide resolved markers?

After partial composition, some markers have been resolved (hole
replaced with source body). By the time skeleton emission runs, those
markers are already gone from the tree. Only *unresolved* markers
survive.

**Recommendation**: this is the natural behavior and matches the
"skeleton = snapshot of the current unresolved state" intuition.
Locked.

### 13.3 Separate function vs mode parameter?

Alternative surfaces considered: `composable.emit_skeleton()` as a
dedicated method vs `emit(mode="markers")` as a parameterized one.

**Recommendation**: `mode` parameter, as documented above. Keeps one
public emission entry point, makes the distinction discoverable in
the docstring, and allows future modes (e.g. typed-comment injection)
to join the same surface.
