# 006: Cross-scope identifier threading — `astichi_import` / `astichi_pass`

Priority: #1 (blocking predictable composition).

Fills in the boundary crossings between Astichi scopes. The within-scope
identifier state grid is 005. The composition model and scope definition
are in `AstichiCompositionModel.md` and the summary.

## Surface

### `astichi_import(name, scope=None)` — declaration form

Joins the inner scope's `name` with the named scope's `name`. All inner
occurrences of `name` rewrite to whatever the named scope supplies.

- Statement position, top of scope body, before non-marker statements.
- `scope=None` (default) = immediately enclosing Astichi scope.
- `scope="global"` = root of this compile unit. Rewritten at splice
  time to the concrete scope id of the wrapping insert node. Does not
  leak past the splice.
- `scope="<insert-marker-id>"` = that specific enclosing scope.
- Semantically equivalent to `name__astichi_arg__` (suffix form). Pick
  whichever reads better at the use site.

### `astichi_pass(name, scope=None)` — expression form

Reads the named scope's builder-parameter `name` and yields its value
at the use site. The inner scope receives a value, not a name.

- Usable wherever an expression is valid: assignment RHS, function
  argument, augmented-assign RHS, etc. Assignment LHS names the inner
  local; `f(astichi_pass(y))` passes straight into the call.
- `scope` argument same as import.
- **Reservation rule**: the builder-side `name` must not appear as any
  other binding in the inner scope. Reject at gate.

## Resolution

| marker | substitution level | inner-scope name | collides-with-local |
|---|---|---|---|
| `import(x)` / `x__astichi_arg__` | name | `x` | local `x` renamed by hygiene |
| `pass(y)` | value | LHS chooses | any other `y` in scope = reject |

Multiple imports resolving to the same external name is fine — just
substitution: `import(a) + import(b)` + builder `a=c, b=c` → all `a`
and `b` become `c`.

## Rejection list

Within one inner scope, for name `x`:

- `import(x)` without binding in the named scope
- `pass(x)` when `x` is also bound elsewhere in the inner scope
- `import(x)` + `x__astichi_keep__` (keep pins inner; import joins outward — contradiction)
- `import(x)` + `pass(x)` (both claim `x` in incompatible ways)
- `scope=` pointing at a scope id that isn't an ancestor of this scope

Everything else is allowed.

## Materialize ordering

Inserted into the 005 pipeline:

1. Gate (all 005 checks + rejection list above).
2. Resolve identifier args / imports (name level). Outside-in: ancestor
   scopes' names finalize first. Atomic per `(stripped_name, scope)`.
3. Resolve passes (value level). Each pass call becomes a reference to
   the named scope's resolved binding.
4. Hygiene.
5. Strip `__astichi_keep__`.
6. Emit.

Post-step-3 invariant: no `astichi_import` / `astichi_pass` call nodes
in the tree.

## Splice-time scope-id rewrite

When a piece containing `scope="global"` (or any piece-relative scope
id) is spliced into a wrapping insert node W, those scope ids are
rewritten to W's scope id as part of `build_merge`. `global` never
survives splice.

## Round-trip

Pre-materialize `emit` preserves both markers and their scope
arguments. `compile(emit(x))` reproduces an equivalent composable.

## Open

- Exact `scope` argument form (string literal vs identifier reference)
  — defer until implementation. Constraint: must survive `emit` /
  `compile` round-trip unchanged.
- Interaction with loop unroll: unroll introduces no fresh scope, so
  pass/import inside an unrolled body inherit the enclosing scope of
  the loop. No new rule required.
