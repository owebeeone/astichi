# 004: materialize accepts code with latent scope-leak / runtime errors

Status: open (Gaps 1, 2, 3); **Gap 4 resolved**
Priority: high (soundness)
Filed: V2 Phase 3 (post-composition-unification)

## Summary

`materialize()` currently accepts and emits Python that can fail at runtime
even when no mandatory demand is outstanding. Four distinct gaps were
found while building the materialize test matrix. Together they allow
`.materialize().emit()` output to be syntactically valid yet semantically
broken, which directly contradicts
`AstichiApiDesignV1-CompositionUnification.md §2.2` ("materialize() on a
closed composable produces executable Python").

Gap 4 has since been closed by the "hygiene runs only when all insert
markers are in place" rule (`AstichiApiDesignV1-CompositionUnification.md`
§2.5(c)); it is retained below for historical record. Gaps 1–3 remain
open design work for V2 Phase 3.

## Gap 1 — Cross-scope free-name fall-through

A contribution inside a fresh Astichi scope can read a name that has no
local binding. `_load_role` in `src/astichi/hygiene/api.py` resolves the
read by falling through to the enclosing scope without recording a
dependency.

### Repro

```python
import astichi

builder = astichi.build()
builder.add.Root(astichi.compile("total = 0\ntotal = astichi_hole(bump)\n"))
builder.add.Step(astichi.compile("astichi_insert(bump, total + 1)\n"))
builder.Root.bump.add.Step()

materialized = builder.build().materialize()
# emits: total = 0\ntotal = total + 1
```

The contribution `Step` references `total` as a free name. Nothing in
`Step`'s surface declares "I need `total` in my host's scope"; the link
is established by accidental name collision with the host.

### Impact

`Step` has no declared input contract for `total`. If `Step` is wired to
a different root that does not define `total`, materialize still
succeeds and the emitted code fails at runtime (see Gap 2).

### Proposal

Free-name reads inside a fresh Astichi scope should either (a) require
an explicit `astichi_bind_external(total)` declaration on the
contribution, or (b) be recorded as a demand port and gated at
materialize. Deciding between (a) and (b) is a design question for V2
Phase 3.

## Gap 2 — Implied demand ports do not gate materialize

`materialize_composable` rejects unresolved demands only when they
carry the `hole` or `bind_external` source. Demands with source
`implied` (free names that `analyze_names` could not resolve) pass
through silently.

### Repro

```python
import astichi

compiled = astichi.compile("result = missing\n")
materialized = compiled.materialize()
# emits: result = missing     # NameError at runtime
```

The `implied` demand for `missing` is visible on
`materialized.demand_ports` but was not an error during materialize.

### Impact

`materialize()` promises executable output. Silent implied demands
break that contract, including the composition-unification idempotency
contract (the round-trip still holds at the AST level, but
`exec(materialize().emit())` raises `NameError`).

### Proposal

Either (a) tighten `materialize()` to reject non-builtin implied demands,
or (b) carry a `strict_mode` flag on `BasicComposable.materialize()`
that opts into this check. Decision deferred to V2 Phase 3.

## Gap 4 — Unmatched `@astichi_insert` shell survives materialize — **resolved**

Status: **resolved** (gate enforcement landed in
`src/astichi/materialize/api.py` alongside the
`AstichiApiDesignV1-CompositionUnification.md §2.5(c)` rule).

The rule that "hygiene runs only when all insert markers are in
place" is now enforced at the materialize gate, before hygiene. Any
unmatched block-form `@astichi_insert(name)` shell (no sibling
`astichi_hole(name)`) or unmatched expression-form
`astichi_insert(name, ...)` (no `astichi_hole(name)` anywhere in the
tree) raises `ValueError` at the gate. The gate is option (a) from
the original proposal; option (b) (silent splice-and-strip) was
rejected because it would grant a "free scope" affordance with no
declared consumer — exactly the kind of undocumented hole that a
code-writing agent will latch onto.

Regression tests live in `astichi/tests/test_materialize.py`:

- `test_materialize_rejects_unmatched_block_insert_shell`
- `test_materialize_rejects_unmatched_expression_insert`

No further work is required for this gap.

## Gap 3 — Self-referential rename produces UnboundLocalError

When a fresh Astichi scope contains `name = name + expr`, the scope
hygiene pass renames both sides to the same fresh identifier. The
generated local is then read before it is written.

### Repro

```python
import astichi

builder = astichi.build()
builder.add.Root(astichi.compile("total = 0\nastichi_hole(body)\n"))
builder.add.Step(astichi.compile("total = total + 1\n"))
builder.Root.body.add.Step()

materialized = builder.build().materialize()
# emits:
#   total = 0
#   total__astichi_scoped_1 = total__astichi_scoped_1 + 1
```

The renamed local reads itself before assignment. This is an
`UnboundLocalError` at runtime even though the host's `total` is still
in scope.

### Impact

Same-scope rebind of an inherited name silently produces dead code.
The user's apparent intent ("read host `total`, compute a new local")
is not expressible under the current hygiene pass without an explicit
shadow or bind declaration.

### Proposal

Detect read-before-first-write inside a fresh Astichi scope when the
read target is the same identifier that hygiene just renamed. Either
(a) raise a diagnostic pointing the user at `astichi_keep` or
`astichi_bind_external`, or (b) leave the pre-rename read free and
only rename subsequent uses. Decision deferred to V2 Phase 3.

## Cross-references

- `AstichiApiDesignV1-CompositionUnification.md §2.2` — executable-output
  contract that these gaps violate.
- `AstichiApiDesignV1-CompositionUnification.md §2.4` — the scope
  isolation rule that Gap 3 correctly implements for writes but
  over-applies across read/write pairs.
- `src/astichi/hygiene/api.py` — location of Gap 1 and Gap 3.
- `src/astichi/materialize/api.py` — location of Gap 2.

## Tests

- An xfail regression for each gap is the suggested first step so the
  issue stays visible during V2 Phase 3 design work. None are landed
  yet; when they are, they should be marked `xfail(strict=True)` and
  unlocked when the design decision above lands.
