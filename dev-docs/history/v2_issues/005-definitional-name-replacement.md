# 005: Identifier-shape input states — surface, builder API, hygiene, materialize, bindability

Status: open
Priority: high (public-surface correctness; completes the composition-model grid)
Filed: V2 (post-composition-unification, during marker-surface audit)

Governing principle: `dev-docs/AstichiCompositionModel.md`. Markers
enumerate input states. The identifier shape currently lacks its state
peers — the existing `__astichi__` / `astichi_definitional_name`
surfaces are a half-implemented single cell. Fill in the grid.

## 1. State grid (identifier shape)

| state              | source surface            | builder surface              |
|--------------------|---------------------------|------------------------------|
| undefined (supply) | `name__astichi_arg__`     | `arg_names=("name", ...)`    |
| defined (keep)     | `name__astichi_keep__`    | `keep_names=("name", ...)`   |
| free               | plain identifier          | n/a (hygiene-managed)        |

Applies to every binding position:

- `ast.FunctionDef` / `ast.AsyncFunctionDef` / `ast.ClassDef` `.name`
- `ast.arg.arg` (parameters)
- `ast.Name` in Store / Load context (variables)
- `ast.Attribute.attr` (attributes, when targeted by an export)
- Every Load-context site where the suffixed name appears (call
  targets, annotations, `astichi_export(...)` arguments, subscript
  values, decorator references, etc.)

Suffix form is required for source; builder form is the out-of-source
equivalent and is mandatory — a caller must be able to compose without
editing the piece's source.

## 2. Occurrence identity — one parameter per (stripped-name, scope)

**An identifier-shape parameter is one logical slot, not one textual
site.** Multiple occurrences of the same suffixed name inside one
Astichi scope denote the **same** parameter and resolve together.

Motivating shape (module-level composition, "astichi_script"):

```python
class foo__astichi_arg__:
    pass

BAR = foo__astichi_arg__()
astichi_export(foo__astichi_arg__)
```

All three `foo__astichi_arg__` occurrences — the `ast.ClassDef.name`
defining binding, the `ast.Name` Load reference inside the call, and
the Load reference passed to `astichi_export` — denote one parameter
and resolve to one name at materialize time. This is the behavior
that makes the surface worth having.

### Rules

1. **Identity key.** A parameter is identified by
   `(stripped_name, enclosing_astichi_scope)`. The suffix is the
   discriminant that says "this is an arg," not an occurrence id.
2. **Scope boundary.** "Astichi scope" is the same concept used
   elsewhere in the pipeline: the module is the outermost Astichi
   scope (the `astichi_script` case); every `astichi_insert` shell
   (decorator or expression wrapper) introduces a fresh Astichi
   scope per `AstichiApiDesignV1-CompositionUnification.md §2`.
3. **Cross-scope isolation.** The same stripped name appearing in a
   different Astichi scope is a **different** parameter. Nested
   `astichi_insert` shells get their own arg slots even when the
   suffixed name matches — matching the hole-name convention for
   expression-shape.
4. **Uniform substitution.** When an arg parameter resolves, every
   occurrence in its scope — regardless of AST node type or context
   — is rewritten to the resolved identifier in a single atomic
   pass. No occurrence may be left suffixed; no occurrence may be
   rewritten to a different name than its siblings.
5. **Port merging.** Port extraction collapses occurrences by
   identity key. The composable exposes **one** `DemandPort(shape=
   IDENTIFIER, name=stripped_name)` per scope, not one per site.
   The port's occurrence list is kept internally for the resolve
   pass but is not part of the public surface.
6. **Definition detection is not required.** Because identity is by
   stripped name and every site resolves together, the resolver does
   not need to distinguish the "defining" occurrence from reference
   occurrences. (This matters for the `ast.Name`-in-Store vs.
   `ast.FunctionDef.name` vs. `ast.ClassDef.name` case, and for
   scripts with no single obvious "definition" site.)

### Why this is trickier than expression-shape

For expression-shape demands, `astichi_hole(x)` is a single-site
marker: the hole IS its occurrence, and the registry maps one hole
id to one expression position. The materialize-time substitution
replaces that one position.

Identifier-shape demands have N occurrences per parameter across
arbitrary AST node types. Implementation must:

- walk every scope collecting every suffixed-name occurrence across
  every node type listed in §1,
- group occurrences by identity key,
- substitute atomically per group at resolve time.

A bug that rewrites fewer than all occurrences, or rewrites
occurrences inconsistently, produces emitted Python that references
an undefined name — a soundness break equivalent to Issue 004
Gap 1 / Gap 2. The resolve pass must assert "no `__astichi_arg__`
suffix remains on any identifier" before handing off to hygiene.

## 3. Bindability (how undefined identifiers get supplied)

An undefined identifier is a demand port of `IDENTIFIER` shape. It can
be satisfied by any of:

1. **Builder wiring from an exported name.** A piece exports an
   identifier via `astichi_export(name)` (or equivalently a
   `name__astichi_keep__` declared public by the builder). The
   builder wires exporter → arg slot:

   ```python
   builder.Step.target.wire_identifier(Other.public)
   # or symmetric to the expression-shape form
   builder.Step.target.add.Other()  # if Other exposes a single public name
   ```

   At build, every occurrence of `target__astichi_arg__` in `Step` is
   rewritten to the exporter's resolved name.

2. **Builder-supplied literal.**
   ```python
   astichi.compile(source, arg_names={"target": "resolved_name"})
   builder.add.Step(Step_src, arg_names={"target": "resolved_name"})
   ```
   Equivalent to an explicit wire from a synthetic identifier
   supply.

3. **Explicit `.bind_identifier(**names)` on a composable**, mirroring
   `bind()` for external values:
   ```python
   piece.bind_identifier(target="resolved_name")
   ```

All three funnel through the same resolve pass described in §2 rule 4:
the `(stripped_name, scope)` group is rewritten in one atomic
substitution and the suffix is stripped from every occurrence.

## 4. Hygiene rules (per state)

- **Free:** standard hygiene. Colliding local names across Astichi
  scopes get renamed apart.
- **Keep:** the stripped name is added to `preserved_names` for its
  scope. Hygiene does not rename it and will not rename other names
  *onto* it.
- **Arg:** the suffixed name is not a binding from hygiene's point of
  view. Scope analysis records an identifier demand per §2 rule 5;
  no rename is applied until the arg is resolved (§5 step 2).

Hygiene runs **once**, inside `materialize`, after all args are
resolved. No materialize call is allowed to run hygiene with
unresolved arg-identifiers remaining.

## 5. Materialize pipeline (identifier shape)

Ordered, same pass as expression-shape:

1. **Gate.** Reject any unresolved `__astichi_arg__` suffix (no
   wiring, no builder param, no `bind_identifier`). Same error class
   as unresolved mandatory hole.
2. **Resolve args.** For each `(stripped_name, scope)` group,
   substitute the resolved identifier across **every** occurrence
   and strip the suffix. After this pass, assert no
   `__astichi_arg__` suffix survives anywhere in the tree.
3. **Hygiene.** Runs with the final name set. Keep names are
   preserved; free names may be renamed across scopes.
4. **Strip keep suffix.** After hygiene, remove `__astichi_keep__`
   from every remaining identifier. The stripped name was already
   pinned in the preserved set, so no collision can occur at this
   point (assert this as an internal invariant).
5. **Emit.** Output source contains neither suffix.

## 6. Builder-API details

- `astichi.compile(source, *, arg_names=None, keep_names=None)` — both
  accept either an iterable of names (keep) or a mapping
  (`arg_names={"target": "resolved"}`). `keep_names` has no resolution
  step; the listed names are added to the preserved set as if they
  bore `__astichi_keep__`.
- `builder.add.Step(piece, *, arg_names=None, keep_names=None)` —
  applied to the named instance only.
- `builder.Step.slot.wire_identifier(other.public_name)` — symmetric
  to `builder.Step.slot.add.Other()` for expression-shape wiring; the
  `public_name` handle comes from an explicit
  `astichi_export(name)` or `name__astichi_keep__` declaration.
- `Composable.bind_identifier(**names)` — returns a new composable with
  the listed args resolved; analogous to `bind(**externals)`.

## 7. Materialize-gate additions

- Unresolved `__astichi_arg__`: `ValueError`, lists name(s) and
  line(s) of **every** occurrence in the scope (not just the first),
  so the user sees the full reach of the unresolved parameter.
- Resolved-but-residual `__astichi_arg__` after the resolve pass:
  internal invariant violation (not a user error).
- Resolved-but-residual `__astichi_keep__` after hygiene: internal
  invariant violation (not a user error).
- `astichi_definitional_name(x)` call form (retired surface): falls
  through to the normal unresolved-name gate (Issue 004 Gap 2) —
  nothing silent.

## 8. Test matrix

Per binding position (FunctionDef / ClassDef / variable / parameter /
attribute) cover:

- Free name: hygiene renames across scopes as today.
- `__astichi_keep__` (source): stripped on materialize, name preserved
  through hygiene, emitted source executable.
- `__astichi_keep__` via `keep_names=` builder param: equivalent.
- `__astichi_arg__` with builder wiring: arg stripped, resolved name
  substituted at every occurrence (including Load / Store / attribute
  context), executable.
- `__astichi_arg__` via `arg_names=` / `bind_identifier`: equivalent.
- `__astichi_arg__` unresolved at materialize: gate raises and the
  message lists all occurrences.
- Collision: outer keep + inner free that would otherwise collide →
  inner gets hygiene-renamed; keep untouched.
- Round-trip: pre-materialize `emit` → `compile` preserves both
  suffixes and arg / keep / export metadata.
- Retired `astichi_definitional_name(x)` call: no silent strip; falls
  through to implied-demand gate (requires Issue 004 Gap 2).

Multi-site identity tests (§2):

- **Script-level (module-scope) arg** appearing simultaneously as a
  `ClassDef.name`, as a `Name(Load)` in a call target, and as the
  `astichi_export(...)` argument — the exact shape from §2. Resolve
  once, all three sites rewritten, emit runs.
- Same, but with `FunctionDef.name` in place of `ClassDef.name`.
- Arg appearing as a variable in Store context and as Load
  references in the same scope — resolved uniformly.
- Arg name shared across two Astichi scopes (outer scope + one
  `astichi_insert` shell): two independent parameters, independently
  resolvable to different names; one of them left unresolved → gate
  raises for that scope only.
- Arg appearing only inside a nested `astichi_insert` shell (not in
  the enclosing scope) — the enclosing scope has no demand for that
  name; the shell does.
- Port-merging: a parameter with N occurrences produces exactly one
  `DemandPort` entry, not N.
- Partial-resolve refusal: no API is allowed to resolve fewer than
  all occurrences of a parameter. If the resolve pass ever leaves a
  suffix behind, the internal invariant assertion fires.

## 9. Migration plan

1. Rename the existing `_DefinitionalNameMarker` to
   `_ArgIdentifierMarker` and change its suffix from `__astichi__` to
   `__astichi_arg__`. Keep the existing `IDENTIFIER`-shape supply-port
   extraction but rebrand as a **demand port** (it was always a
   demand; current code mis-classified it as a supply).
2. Add `_KeepIdentifierMarker` with suffix `__astichi_keep__`. No
   port; contributes to the preserved-name set.
3. Generalize both suffix markers to apply to every node type listed
   in §1 — `ast.FunctionDef` / `ast.AsyncFunctionDef` /
   `ast.ClassDef` / `ast.arg` / `ast.Name` / `ast.Attribute`, in both
   Load and Store contexts. A single visitor in
   `src/astichi/lowering/markers.py` handles all positions.
4. Extend `src/astichi/model/ports.py` to produce one merged
   `DemandPort(shape=IDENTIFIER)` per `(stripped_name, scope)`
   group per §2 rule 5. The occurrence list is kept internally for
   the resolve pass.
5. Implement the arg-resolve pass in
   `src/astichi/materialize/api.py` (before hygiene) per §2 rule 4.
   Include the post-pass assertion that no `__astichi_arg__` suffix
   survives.
6. Implement the keep-suffix-strip pass (after hygiene).
7. Add the builder / composable API surfaces enumerated in §6.
8. Add the gate checks enumerated in §7.
9. Remove `"astichi_definitional_name"` from `_RESIDUAL_MARKER_NAMES`
   (so the call form no longer silently disappears).
10. Update `AstichiApiDesignV1-CompositionUnification.md` §§2.5, 4, 6
    with the new identifier-shape behaviors and gate entries.
11. Add the test matrix from §8.

## 10. Cross-references

- `dev-docs/AstichiCompositionModel.md` — governing principle.
- `AstichiApiDesignV1-CompositionUnification.md` — materialize gate,
  strip, round-trip; §2 scope-boundary definitions referenced by §2
  above.
- `004-materialize-free-name-soundness.md` — Gap 2 is the destination
  for any `astichi_definitional_name(x)` call left in user source
  after this issue lands; a bug in the §5 step 2 resolve pass would
  manifest as a new variant of Gap 1 / Gap 2.
- `src/astichi/lowering/markers.py:78` — current definitional-name
  marker, to be renamed.
- `src/astichi/model/ports.py:125` — supply-port branch to be
  reworked into a demand-port branch (the `shape=IDENTIFIER`
  construction site).
- `src/astichi/materialize/api.py:932` — `_RESIDUAL_MARKER_NAMES` to
  be trimmed.
