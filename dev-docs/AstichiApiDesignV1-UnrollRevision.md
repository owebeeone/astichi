# Astichi API design V1: loop unroll revision

This document re-instates `astichi_for` loop unrolling for V1, after it was
deferred during the milestone-5 planning pass.

It supersedes the deferral note in `historical/V1Plan.md` section `5b`. Once accepted,
loop unrolling becomes a tractable V1 feature instead of a future milestone.

This note is directional. It is meant to prevent semantic drift before the
unroller is implemented.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md` (especially §5.7, §9.2, §16.1)
- `astichi/dev-docs/AstichiApiDesignV1-InsertExpression.md`
- `astichi/dev-docs/IdentifierHygieneRequirements.md`
- `astichi/dev-docs/historical/V1Plan.md` (5b deferral notice — superseded
  by this doc; V2 reinstates unroll in `V2Plan.md`)

## 1. Why loop unrolling was deferred

The original deferral cited three sources of complexity:

1. **Timing**: when does unrolling happen?
2. **Nested loop dependencies**: an inner loop's domain may depend on the
   outer loop's iteration value, so the inner cannot resolve until the outer
   has.
3. **Copy-paste hygiene**: each iteration produces a copy of the loop body,
   and per-copy hygiene was thought to require fresh scope boundaries.

This document collapses all three by adding a single hard precondition.

## 2. The reframing precondition

> **Loop parameters must be fully resolved before any loop-expanded binding
> is allowed to be addressed.**

Once that constraint is accepted:

1. **Timing** is no longer a problem — there is exactly one unroll moment
   (build time), and after it the graph is a flat graph with more named
   targets.
2. **Nested loops** resolve in a single recursive pass: outer first
   (literal domain), substitute the outer iteration value into the inner
   domain expression, inner is now also a literal domain, recurse.
3. **Copy-paste hygiene** is just **macro expansion**, not scope
   introduction (see §6).

## 3. Unroll trigger and the all-or-nothing rule

### 3.1 Trigger: auto-detect from indexed addressing

Unrolling happens **at `build()` time**, as a discrete first pass before
edge resolution.

The trigger is the **presence of any indexed edge in the builder graph**
(any recorded `TargetRef` with a non-empty `path` tuple). The builder
already tracks this: `TargetHandle.__getitem__` accumulates the path, and
any edge whose target has `path != ()` is an indexed edge.

Build-time behavior:

- **At least one indexed edge present** → unroll every `astichi_for` loop
  in every instance. Loops are flattened into the enclosing scope, the
  `for ... in astichi_for(...)` statement is removed, and synthetic
  per-iteration target names become addressable.
- **No indexed edges present** → no loops are unrolled. Every
  `astichi_for` loop remains as-is in the resulting `Composable`.

This preserves §10.1 of the main design ("`build()` must not force eager
unrolling"): a graph with no indexed addressing does not unroll. The trigger
is exactly the user's own signal that they rely on per-iteration targets.

### 3.2 Explicit override

`build()` also accepts an explicit `unroll` parameter for users who want
deterministic control:

```python
builder.build()                 # auto-detect (default)
builder.build(unroll=True)      # force unroll even with no indexed edges
builder.build(unroll=False)     # force no unroll even with indexed edges
builder.build(unroll="auto")    # explicit auto-detect (same as default)
```

Forcing `unroll=True` with no indexed edges is legal — it produces a
loop-free composable even without addressing. This is useful when the user
wants to feed the composable to `materialize()` (which requires loop-free
input; see §9).

Forcing `unroll=False` with indexed edges is a user error guard: edge
resolution will fail because the synthetic per-iteration targets do not
exist. The resulting error names the offending addresses and suggests
removing the override.

### 3.3 The all-or-nothing rule

> **If unrolling is triggered, every `astichi_for` loop in the graph must
> be resolvable. Partial unrolls are an error.**

Rationale: a graph that mixes "unrolled" and "still-loop" forms in the
same build is structurally ambiguous. The user should not have to reason
about which targets resolved synthetically and which remain loop-shaped.

For V1 (literal-domain only — see §7), every loop is self-resolving from
its literal AST, so the check is: if any `astichi_for` loop has a
non-literal domain, unrolling fails before any copies are produced.

For future external-domain support (deferred — see §10), the parameter
dict must contain an entry for every external-domain loop in the graph;
missing entries are an error before any unrolling begins.

### 3.4 No referencing before unroll

Loop-expanded target addressing is recorded by the builder but **not
validated until after the unroll pass completes**. The builder fluent API
permits `a.slot[i].add.B(order=N)` at any time — the call records a
`TargetRef` with `path=(i,)` and an additive edge. Translation of the
`(target_name, path)` pair to the synthetic per-iteration target
(`target_name__iter_i`) happens during edge resolution, after unrolling.

This means the builder can be used in any order: wire first, then unroll;
or unroll first, then wire. Both produce the same graph because edges are
resolved against the post-unroll target namespace.

## 4. `__iter_i` — per-iteration target renaming

### 4.1 What gets renamed

Only `astichi_hole(target)` markers are renamed per iteration copy. The
target name is suffixed with `__iter_<i>` for the outermost loop's
iteration index, `__iter_<i>_<j>` for the next nested loop, and so on.

```python
for x in astichi_for((10, 20)):
    astichi_hole(slot)
```

Unrolled output:

```python
astichi_hole(slot__iter_0)
astichi_hole(slot__iter_1)
```

Nested:

```python
for x, y in astichi_for(((1, 2), (2, 1))):
    astichi_hole(first)
    for a in astichi_for(range(y)):
        astichi_hole(second)
```

After substituting `y` and recursively unrolling:

```python
astichi_hole(first__iter_0)
astichi_hole(second__iter_0_0)
astichi_hole(second__iter_0_1)
astichi_hole(first__iter_1)
astichi_hole(second__iter_1_0)
```

This matches the addressing examples in §9.2 and §16.1 of the main API
design exactly:

| Address | Synthetic target name |
|---------|----------------------|
| `A.first[0]` | `A.first__iter_0` |
| `A.first[1]` | `A.first__iter_1` |
| `A.second[0, 0]` | `A.second__iter_0_0` |
| `A.second[0, 1]` | `A.second__iter_0_1` |
| `A.second[1, 0]` | `A.second__iter_1_0` |

### 4.2 What is NOT renamed

Other name-bearing markers refer to **Python-level identifiers**, not
invented marker target names, and are not renamed:

| Marker | Argument refers to | Renamed per iter? |
|--------|--------------------|-------------------|
| `astichi_hole(slot)` | invented marker-target name | **YES** |
| `astichi_keep(name)` | Python preserved name | NO |
| `astichi_bind_external(name)` | externally supplied Python name | NO |
| `astichi_bind_once(name, value)` | Python binding | NO |
| `astichi_bind_shared(name, value)` | Python binding | NO |
| `astichi_export(name)` | Python public binding | NO |
| `astichi_definitional_name(name)` | Python def/class site | NO |
| `@astichi_insert(target)` (decorator) | refers to a hole's target | NO direct rename — addressing handles `[i]` |
| `astichi_insert(target, expr)` (call) | refers to a hole's target | NO direct rename — addressing handles `[i]` |

### 4.3 Constraint on non-`astichi_hole` name-bearing markers inside loops

Placing a non-`astichi_hole` name-bearing marker inside an `astichi_for`
body is rejected at unroll time. Examples that fail:

- `astichi_export(out)` inside a loop body: would produce N export sites
  with the same Python name, which is semantically a port-conflict error.
- `astichi_bind_external(items)` inside a loop body: the external name has
  no per-iteration variant.

This restriction keeps V1 unrolling simple and consistent. Users that need
per-iteration exports can name them explicitly outside the loop.

## 5. Loop variable substitution

### 5.1 What "substitute" means

After deep-copying the loop body for iteration `i`, every `ast.Name(id=v,
ctx=ast.Load())` reference where `v` is a loop variable is replaced with
the corresponding iteration value, encoded as `ast.Constant(value=...)`.

Concretely, for:

```python
for x in astichi_for((10, 20, 30)):
    arr[x] = x + 1
    astichi_hole(slot)
```

Iteration 0 (`x = 10`):

```python
arr[10] = 10 + 1
astichi_hole(slot__iter_0)
```

Iteration 1 (`x = 20`):

```python
arr[20] = 20 + 1
astichi_hole(slot__iter_1)
```

Iteration 2 (`x = 30`):

```python
arr[30] = 30 + 1
astichi_hole(slot__iter_2)
```

### 5.2 Substitution scope

- Only `Load` context references are substituted. `Store` context targets
  are left alone.
- Tuple unpacking targets are bound element-wise: `for x, y in
  astichi_for(((1, 2), (2, 1)))` binds `x` and `y` independently per
  iteration. Both are eligible for substitution.
- Substitution is structural — it walks the body subtree and replaces
  matching `ast.Name(Load)` nodes regardless of nesting depth.
- **No constant folding.** `arr[10] = 10 + 1` is emitted as-is rather
  than `arr[10] = 11`. Folding is left for downstream tools or future
  passes; the unroller's job is to substitute, not to optimize.

### 5.3 Loop variable shadowing is scope-aware

Substitution is **scope-aware**: the unroller walks the loop body and
substitutes `Name(Load)` references to the loop variable only while the
loop variable's name has not been re-bound by an inner scope.

Rules:

- **Same-scope rebinding is rejected.** A loop variable that is re-bound
  in the same scope as the `astichi_for` (e.g. `x = something` at the top
  level of the loop body when `x` is the loop variable) is a user error.
  The unroller raises at unroll time with a clear message.
- **Inner-scope shadowing is respected.** When an inner scope re-binds the
  loop variable name — function parameters, lambda parameters, class
  scope, comprehension targets, nested `astichi_for` loops with the same
  variable — substitution halts at that scope boundary. References to the
  same name inside that inner scope are left alone.

Concretely:

```python
for x in astichi_for((1, 2)):
    # Same-scope rebind — REJECTED:
    # x = 99

    # Inner-scope shadowing — OK, substitution halts at `f`'s scope:
    def f(x):
        return x            # this x is f's parameter, not the loop var

    # Lambda parameter — OK:
    g = lambda x: x + 1

    # Comprehension target — OK (comprehension has its own scope):
    pairs = [(x, y) for x, y in items]

    # Nested astichi_for with the same variable name — OK:
    for x in astichi_for((10, 20)):
        astichi_hole(slot)  # x here is the inner loop var
```

This matches Python's own name-resolution model. The unroller's
substitution visitor maintains a "currently-shadowed" set as it descends
into inner scopes and restores the prior state on exit.

#### 5.3.1 Scope boundaries recognized for shadowing

- `ast.FunctionDef` / `ast.AsyncFunctionDef` parameters and body
- `ast.Lambda` arguments
- `ast.ClassDef` body (class scope)
- Comprehension expressions (`ast.ListComp`, `ast.SetComp`, `ast.DictComp`,
  `ast.GeneratorExp`) — their target variables create a nested scope
- Nested `astichi_for` loops that re-bind the same variable name
- Walrus targets (`(x := ...)`) at the top level — **rejected** as
  same-scope rebinding per the rule above

### 5.4 Nested-domain substitution

In a nested loop, the inner loop's domain expression is part of the outer
loop's body and is substituted normally. So `for a in astichi_for(range(y)):`
becomes `for a in astichi_for(range(2)):` (in iteration 0) or
`for a in astichi_for(range(1)):` (in iteration 1) before the inner unroll
runs. After substitution, the inner domain is itself a literal — recurse.

### 5.5 Markers may not take a loop variable as their name argument

A name-bearing marker whose identifier argument is an enclosing loop
variable is **rejected at unroll time**. Example:

```python
for x in astichi_for((1, 2)):
    astichi_keep(x)     # REJECTED
    astichi_hole(x)     # REJECTED
    astichi_export(x)   # REJECTED
```

Reason: substitution would replace `Name("x", Load)` with `Constant(1)`
etc., turning the marker argument into a literal value. That violates the
"marker argument must be a bare identifier" contract enforced by the
lowering validators, and the semantic intent is unclear (there is no
per-iteration version of a `keep` or `export` that makes sense).

The check is syntactic: any name-bearing marker whose `ast.Name` argument
matches an enclosing-loop variable name fails. Detection happens before
substitution so the error clearly attributes the conflict to the loop
variable rather than to a downstream lowering-validator failure.

## 6. Hygiene posture: copies share a scope

> **Unrolled loop copies do not introduce fresh Astichi scope boundaries.**

This is the critical correction over an earlier draft. Loop unrolling is
**macro-style expansion** — duplicate the body N times in the enclosing
Python scope, exactly as if the user had written it out by hand.

### 6.1 Why no fresh scopes

A Python `for x in iterable:` loop body does not introduce a new scope. The
loop variable leaks into the enclosing scope. If unrolling introduced fresh
scopes per copy, common patterns would silently break:

```python
total = 0
for x in astichi_for((1, 2, 3)):
    total = total + x
```

With fresh scopes per copy, the three `total = total + x` statements would
each rename `total` independently (e.g., `total__astichi_scoped_0`, `_1`,
`_2`) and the accumulator would never accumulate. The user's mental model
is "this is identical to writing the three additions out by hand," and only
shared-scope semantics preserves that.

Similarly, an `astichi_insert(slot, value)` reference inside an unrolled
loop must resolve to the same outer identifier across all copies. With
fresh scopes per copy, each `slot` reference would resolve to a distinct
freshly-renamed identifier, and a single `astichi_insert` could not fill
all of them. The all-or-nothing addressing model relies on per-iteration
**target renaming** (§4) to disambiguate, not per-copy **scope** isolation.

### 6.2 Concrete contrast

| Operation | Fresh Astichi scope? |
|-----------|----------------------|
| `astichi_insert(target, expr)` (per 4j) | **Yes** — inserted expression is a stranger's code |
| Loop unroll copy | **No** — your own code, duplicated in your own scope |

### 6.3 Implication: name clashes are the user's problem

Because copies share a scope, a body like:

```python
for x in astichi_for((1, 2)):
    result = compute(x)
```

unrolls to two `result = compute(...)` assignments to the same `result`.
The second stomps the first. This matches manual copy-paste. Users that
need distinct per-iteration locals must name them explicitly (e.g.,
`result_0`, `result_1`).

### 6.4 No change to `_FreshScopeCollector`

The unroller does not register copies with the existing
`_FreshScopeCollector` (used by 4d–4f and 4j). Per-call expression-insert
sites continue to be the only fresh Astichi scope boundaries.

## 7. Domain support (V1-lite)

V1 unrolling supports **literal-resolvable** domains only:

- Tuple literals: `astichi_for((1, 2, 3))`, `astichi_for(((1,2), (2,1)))`
- List literals: `astichi_for([1, 2, 3])`
- `range(...)` with integer literal arguments:
  - `astichi_for(range(N))` where `N` is an `ast.Constant(int)`
  - `astichi_for(range(start, stop))`, `astichi_for(range(start, stop, step))`
- Domains that become literal after substitution (nested case): e.g.
  `astichi_for(range(y))` becomes `astichi_for(range(2))` after `y` is
  substituted.

The following are **rejected** at unroll time:

- Free names: `astichi_for(my_iterable)` where `my_iterable` is not a
  literal or a substituted loop variable.
- Function calls other than `range(...)`: `astichi_for(list(...))`,
  `astichi_for(itertools.product(...))`, etc.
- Comprehensions: `astichi_for([x for x in ...])`.
- Arbitrary runtime iterables.

This matches the "phase-1 supported domain categories" already documented
in the main API design §5.7.

## 8. Builder API surface

### 8.1 `build()` signature

```python
result = builder.build(unroll="auto")
```

The `unroll` parameter accepts:

| Value | Meaning |
|-------|---------|
| `"auto"` (default) | Unroll iff any indexed edge is present in the graph (§3.1). |
| `True` | Force unroll regardless of edge shape. |
| `False` | Force no unroll. Any indexed edge fails at resolution (§3.2). |

V1 accepts the boolean aliases `True`/`False` and the string `"auto"`.
The default is `"auto"`.

### 8.2 Forward-compatible parameter shape (deferred)

Future versions extending the surface to external-domain loops are
expected to take a parameter dict:

```python
result = builder.build(unroll={"loop_id": [...], ...})
```

with the all-or-nothing rule (§3.3) enforced. The tri-state V1 surface
(`"auto"` / `True` / `False`) remains valid; the dict form is an
additional accepted shape for supplying external domains. The boolean
`True` is equivalent to `unroll={}` once the dict form lands — "unroll,
no externals to provide."

### 8.3 Edge addressing unchanged

`TargetHandle.__getitem__` (already implemented in 4b) accumulates the
path tuple. No changes to the addressing surface. After unrolling, edge
resolution translates the `(target_name, path=(i,))` pair to the
synthetic target `target_name__iter_i`.

Validation of indexed addresses happens **at edge resolution time**, not
at the moment of `__getitem__`. Rationale:

- The builder cannot know at `__getitem__` time whether the target is a
  loop-expanded slot without inspecting the source tree of the
  target's instance. Delaying validation keeps the builder decoupled
  from AST traversal.
- At edge resolution, the post-unroll target namespace is known
  authoritatively; any missing synthetic target produces a precise
  error.

If the synthetic target does not exist at resolution time — for example,
the user addressed `slot[5]` but the loop only had three iterations, or
`unroll=False` was set explicitly so the synthetic names were never
created — edge resolution fails with a clear message that names the
offending edge, shows the path tuple, and (when applicable) suggests
enabling unroll.

### 8.4 Build sequencing (post-condition)

When unrolling is triggered (auto or explicit `True`):

1. All `astichi_for` loops have been removed from every instance tree.
2. Loop-expanded target names exist as flat synthetic targets.
3. All edges have been resolved against the post-unroll namespace.
4. The returned `Composable` is loop-free.

When unrolling is suppressed (auto-detect found no indexed edges, or
explicit `False`):

1. All `astichi_for` loops remain in their original form in every
   instance tree.
2. Indexed edges (`a.target[i]`) registered against loop-expanded
   targets — if any — fail at edge resolution because the synthetic name
   does not exist. Under `"auto"` this case is impossible by
   construction; under explicit `False` it surfaces the user's override.
3. The returned `Composable` retains its loop-shaped structure for
   later passes.

## 9. Materialize and emit interactions

`materialize()` closes a composable for runnable/emittable output.
`astichi_for` is a compile-time construct that is not valid runtime
Python — it must be fully unrolled before `materialize()` produces its
artifact.

Rules:

- `materialize()` rejects any composable whose tree still contains an
  unresolved `astichi_for` call. The error names the loop's source
  location and instructs the user to call `build(unroll=True)` (or to
  reach unroll through indexed addressing) before materializing.
- A composable produced by `build(unroll="auto")` with indexed edges is
  loop-free and materializes normally.
- A composable produced by `build(unroll=True)` is always loop-free.
- A composable produced by `build()` on a graph with no `astichi_for`
  loops at all is already loop-free and materializes normally regardless
  of the `unroll` setting.
- A composable that retains loops (no indexed edges, default auto) can
  still participate in further composition via another `build()` call;
  materialization is simply deferred until the composable is loop-free.

The `astichi_for` marker is exclusively a build-time construct. It
never appears in materialized or emitted source.

Provenance (6b) and round-trip (6c) work unchanged on the unrolled tree.

## 10. Future extensions (deferred)

Out of scope for the V1 unroll revision (still deferred):

- **Runtime-supplied external-domain loops via `build(unroll={...})`**:
  a per-loop parameter dict supplied directly at build time (§8.2
  sketch). Requires the all-or-nothing rule enforced over that map.
- **Comprehension domains**: `astichi_for([x for x in source])`.
- **Runtime iterables / arbitrary calls**: anything not
  literal-reducible at build time.
- **Constant folding** of substituted bodies.
- **Same-scope rebind of a loop variable as a supported pattern**
  (§5.3 rejects this; V2 keeps the rejection. Cross-scope shadowing
  via an inner function/comprehension/for-target is already supported
  by scope-aware substitution).

Explicitly **in scope for V2** (clarifying prior confusion):

- **Post-bind literal domains**: `astichi_for(fields)` where `fields`
  has been satisfied by `composable.bind(fields=(...))` before unroll
  runs. The substitution pass replaces the external name with an
  `ast.Tuple` / `ast.List` literal, which the unroll pass then treats
  identically to a source-written literal. No per-loop parameter map
  is needed because the domain has been materialised into the tree
  by the time the unroller inspects it. See
  `AstichiApiDesignV1-BindExternal.md §8` for the sequencing contract
  (bind runs before unroll).

Future extensions can be addressed as separate follow-up work once
V1-lite unrolling is in production use.

## 11. Implementation outline

Elaborated in `V2Plan.md` (Phase 2). Sketch:

1. **New module** `astichi/materialize/unroll.py` with a pure-AST
   `unroll_loops(tree)` pass (and helpers).
2. **Unroll pass** walks every `ast.For` whose iter is
   `astichi_for(...)` and, in order:
   - Validates that no non-`astichi_hole` name-bearing marker appears in
     the body (§4.3).
   - Validates that no name-bearing marker's identifier argument is an
     enclosing-loop variable (§5.5).
   - Validates same-scope loop-variable rebinding (§5.3).
   - Validates the domain is literal-resolvable (§7). Non-literal domains
     abort the pass before any copies are produced (§3.3).
   - For each iteration value, deep-copies the body, substitutes loop
     variables using a **scope-aware visitor** that halts at inner scope
     boundaries (§5.3.1), and renames `astichi_hole` targets per
     iteration (§4).
   - Recurses on nested `astichi_for` loops after substitution (each
     nested domain is itself a literal at that point).
   - Replaces the outer `For` node with the concatenated bodies.
3. **`build()` signature**: `build(unroll: bool | str = "auto")`.
   - `"auto"` (default): inspect `graph.edges` for any edge with a
     non-empty `path` tuple. If any exists, trigger unroll; otherwise
     skip.
   - `True`: trigger unroll unconditionally.
   - `False`: skip unroll unconditionally (indexed edges will fail at
     resolution — §3.2).
4. **Edge resolution** maps `(target_name, path=(i,...))` to
   `target_name__iter_<i>...` via the same target-lookup already used
   for block holes. Missing targets produce clear errors (§8.3).
5. **Hygiene machinery unchanged** — copies share scope by
   construction; `_FreshScopeCollector` is not extended.
6. **Materialize** gains a pre-check that rejects composables still
   containing `astichi_for` calls (§9).
7. **Tests** cover: literal-tuple unroll; literal-list unroll;
   `range(N)` / `range(start, stop)` / `range(start, stop, step)` with
   int literals; nested loops with inner-domain substitution; per-copy
   marker target renaming; scope-aware shadowing (lambda, nested
   function, comprehension, nested loop with same variable);
   same-scope-rebind rejection; marker-argument-is-loop-var rejection;
   non-literal-domain rejection; `unroll=True` with no indexed edges;
   `unroll=False` with indexed edges (failure); `"auto"` with no
   loops; `"auto"` with loops but no indexed edges (no-op); `"auto"`
   with loops and indexed edges (unroll).
