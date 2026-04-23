# Astichi V3 target: additional hole shapes

Status: non-normative brainstorm

This note captures design space around additional hole/target shapes beyond the
current V1/V2 model. It is intentionally broad. The goal is not to lock
semantics now, but to avoid forgetting viable directions.

Parameter holes have since been split into the focused
`AstichiV3ParameterHoleSpec.md` and implemented as an initial slice. This
brainstorm keeps parameter mentions as historical context for the broader typed
list-field design space.

## 1. Current boundary

Today Astichi models these insertion families reasonably well:

- block statement lists
- scalar expression positions
- positional variadic expression positions via `*`
- named variadic expression positions via `**`
- dict-entry-like expansion via named variadic dict machinery

The current `astichi_insert` story is strong for:

- inserting statements into a body
- inserting an expression into an expression hole
- ordering multiple inserts where the target is variadic or block-shaped

The current model is weak for:

- adding a new `except` handler
- adding a new `elif` clause
- adding a new `case` clause
- other typed AST list fields that are neither plain statements nor plain
  expressions

## 2. Core observation

The current insertion unit is either:

- a block of statements
- an expression

But Python has many syntactic units that are neither:

- `ExceptHandler`
- `match_case`
- `elif` clause
- `withitem`
- decorator entry
- function parameter (implemented separately as `PARAMETER`)
- class base / class keyword entry
- import alias entry
- comprehension generator

So the general question is:

- should Astichi grow more typed insertion units?

Likely yes, if it wants to compose more of Python cleanly.

## 3. Strong design instinct: whole-unit modeling

The cleanest direction is:

- do not split structured clauses into header/body sub-holes unless there is a
  very strong reason
- instead model the whole Python unit

Good examples:

- whole `except` clause
- whole `elif` clause
- whole `match case`
- whole `try` statement
- whole `if`/`elif`/`else` chain
- whole `with` statement

Why:

- ordering belongs to the whole clause, not its pieces
- scoping often belongs to the whole clause, not its pieces
- header/body cardinality stays aligned
- users reason in Python units, not AST fragments

Bad split examples:

- separate catch-type hole and catch-body hole
- separate case-pattern hole and case-body hole
- separate elif-test hole and elif-body hole

Those drift easily.

## 4. Body-only extensions that probably fit today

Some new targets may not need new payload shapes at all.

These are just body block targets:

- `finally` body
- `else` body on `if`
- `else` body on `for` / `while`
- `else` body on `try`
- body of an existing `except`
- body of an existing `case`

These probably fit the current block insertion model:

- `A.try1.finally_body`
- `A.if1.else_body`
- `A.loop1.else_body`
- `A.try1.excepts[0].body`
- `A.match1.cases[0].body`

Multiple inserts would just accumulate statements in order.

## 5. Clause-list targets that do not fit today

These require something beyond block/expr:

- additional `except` handlers
- additional `elif` clauses
- additional `case` clauses
- maybe additional decorators
- maybe additional `with` items

These are best thought of as typed list-field targets:

- `A.try1.excepts`
- `A.if1.elifs`
- `A.match1.cases`
- `A.func1.decorators`
- `A.with1.items`

Then the inserted thing is a whole clause/item of the appropriate type.

## 6. Statement and clause shape inventory

Potential future Astichi shapes:

- `stmt`
  - one whole statement
- `stmt_block`
  - zero or more statements
- `elif_clause`
  - one condition plus one body
- `except_clause`
  - optional type, optional alias, one body
- `case_clause`
  - pattern, optional guard, one body
- `with_item`
  - context expr + optional `as`
- `decorator`
  - one decorator entry
- `parameter`
  - implemented separately for function signatures; see
    `AstichiV3ParameterHoleSpec.md`
- `arg_entry`
  - one argument entry
- `class_base`
  - one base class entry
- `class_keyword`
  - one class keyword entry
- `import_alias`
  - one import alias entry
- `comprehension_generator`
  - one `for ... in ... if ...` generator

Possibly even:

- `pattern`
- `guard`
- `assignment_target`
- `annassign_target`
- `namedexpr_target`

But those last ones get much more dangerous quickly.

## 7. Whole-statement supplies

One direction is to let a composable supply an entire statement form:

- full `if`
- full `try`
- full `match`
- full `for`
- full `while`
- full `with`
- full `def`
- full `class`

This is conceptually simple:

- they are just `stmt` supplies
- they insert into statement-list targets

What this does not solve:

- extending an existing `try` with a new `except`
- extending an existing `if` with a new `elif`
- extending an existing `match` with a new `case`

So whole-statement supplies are useful, but not sufficient.

## 8. Whole-clause supplies

This is likely the real missing family.

Examples:

- one `except` handler
- one `elif`
- one `case`

These could be inserted into typed clause-list targets:

- `A.try1.excepts.add.B(order=10)`
- `A.if1.elifs.add.C(order=10)`
- `A.match1.cases.add.D(order=10)`

This gives a natural place for ordering:

- lower `order` first
- ties resolved by insertion order, same as other variadic targets

## 9. Candidate source surfaces

The current `astichi_insert` surface is likely not enough by itself for clause
supplies, because the payload is not a plain expr or block.

Possible surfaces:

### 9.1 Decorator-based clause markers

Examples:

```python
@astichi_except(A.try1.excepts, ValueError, order=10)
def handle(err):
    log(err)
```

```python
@astichi_elif(A.if1.elifs, x > 0, order=10)
def positive():
    return 1
```

```python
@astichi_case(A.match1.cases, <pattern>, order=10)
def branch():
    ...
```

Pros:

- human-readable
- preserves clause-body grouping
- `order` has an obvious home

Cons:

- `case` pattern is not an expression
- function wrapper may be semantically weird for some clause kinds

### 9.2 Wrapper call forms

Examples:

```python
astichi_except(A.try1.excepts, ValueError, as_name=err, body=...)
astichi_elif(A.if1.elifs, x > 0, body=...)
```

Pros:

- direct expression-shaped syntax

Cons:

- body encoding becomes awkward
- usually devolves into mini-AST-in-source tricks

### 9.3 Block macro forms

Examples:

```python
with astichi_except(A.try1.excepts, ValueError, order=10) as err:
    log(err)
```

```python
with astichi_elif(A.if1.elifs, x > 0, order=10):
    return 1
```

Pros:

- body is natural Python block syntax

Cons:

- not valid Python as-is without runtime support tricks
- `with` changes local syntax meaning

### 9.4 Docstring-ish / macro-ish hidden forms

Examples:

- specially tagged defs/classes
- special comments
- reserved naming patterns

Pros:

- can be parseable

Cons:

- uglier
- more magical

## 10. `except` design space

Likely the cleanest clause candidate.

Whole-unit components:

- exception type expression
- optional `as name`
- body block

Important semantics:

- order matters
- `except ... as name` creates special binding lifetime semantics
- the alias must stay tied to the body

This strongly suggests whole-clause modeling.

Bad idea:

- `ctch[exp]`
- `ctch[as]`
- `ctch[body]`

Why bad:

- cardinality drift
- body can detach from alias/type
- scope for alias becomes ambiguous

Better:

- one inserted catch clause object

Speculative surface:

```python
@astichi_except(A.try1.excepts, ValueError, order=10)
def handle(err):
    print(err)
```

Interpretation:

- target: `A.try1.excepts`
- type expr: `ValueError`
- alias: first function param if present
- body: function body

Other possibilities:

- no params means no `as`
- more than one param invalid

## 11. `elif` design space

Likely easier than `except`.

Whole-unit components:

- test expression
- body block

No new Python lexical scope.

Speculative surface:

```python
@astichi_elif(A.if1.elifs, x > 0, order=10)
def branch():
    return 1
```

This seems reasonably clean.

Alternative:

- treat `elif` as sugar for another `if` inserted into `else`

But that is semantically noisy and less readable than a real `elif` clause.

## 12. `case` design space

This is the hardest one.

Whole-unit components:

- pattern
- optional guard
- body

Key problem:

- pattern syntax is not ordinary expression syntax

This makes a clean decorator surface harder:

```python
@astichi_case(A.match1.cases, ???, order=10)
def branch():
    ...
```

Questions:

- how is the pattern represented?
- how are capture names represented?
- how is guard attached?

Possible directions:

### 12.1 Dedicated pattern DSL

- explicit Astichi pattern surface
- probably verbose

### 12.2 Reserved wrapper that takes source text

- ugly but practical

### 12.3 Function name / signature tricks

- probably too magical

### 12.4 Defer `case` until pattern composition has a real design

This may be the most sane option.

## 13. `finally` and `else` design space

These probably do not need new clause shapes if the target is only the body.

Examples:

- `A.try1.finally_body`
- `A.try1.else_body`
- `A.if1.else_body`
- `A.while1.else_body`
- `A.for1.else_body`

These can probably stay block-shaped singleton targets.

Multiple inserts would just extend the body in order.

## 14. `with` item design space

Potential target:

- extend a `with` statement with additional items

Example:

```python
with a(), b():
    ...
```

Could imagine inserting a `with_item`.

But this has awkward semantics:

- order matters strongly
- `as name` introduces names in the surrounding scope
- multiple context managers have runtime ordering effects

Still possible, but probably later than `except` / `elif`.

## 15. Decorator-list targets

Potential target:

- add decorators to existing def/class

This is structurally simple:

- decorators are ordered expression entries

Possible target:

- `A.func1.decorators`
- `A.class1.decorators`

This may actually be one of the easiest typed-list targets after `elif`.

## 16. Parameter-list and argument-entry targets

Potential targets:

- add function parameters
- add call arguments as single entries
- add class bases as single entries
- add import aliases

These all point toward a more general model:

- typed list-field extension

Example list fields:

- `arguments.args`
- call `args`
- call `keywords`
- class `bases`
- class `keywords`
- import `names`

This is attractive because it unifies many cases.

It is also dangerous because each field has different validity rules.

## 17. General typed-list-field model

One larger design path:

- every AST list field could become a typed extension point

Examples:

- stmt list
- expr list
- keyword list
- except-handler list
- match-case list
- decorator list
- with-item list
- import-alias list

Then Astichi would have:

- typed targets
- typed supplies
- compatibility by field kind

This is elegant internally.

It may be too abstract for users unless surfaced carefully.

## 18. Scope questions that matter

Some clause kinds are mostly syntactic.

Others carry serious binding semantics:

- `except ... as err`
- `with ... as f`
- pattern capture in `case`
- loop targets
- comprehension generators

Any design that splits these apart risks breaking hygiene.

This is the strongest argument for whole-clause modeling.

## 19. Ordering semantics

Current Astichi ordering discipline can likely extend:

- list-like targets accept multiple inserts
- lower `order` first
- equal `order` uses insertion order

This seems reasonable for:

- `excepts`
- `elifs`
- `cases`
- decorators
- with items

Singleton targets would reject multiplicity or merge bodies if they are
block-shaped:

- `finally_body`
- `else_body`

## 20. Current `astichi_insert` compatibility

The current marker model is enough for:

- block body extension targets
- expr extension targets

It is not enough by itself for:

- clause supplies like `except`, `elif`, `case`

Possible reuse:

- keep `astichi_insert` for body targets
- add sibling clause markers for clause-list targets

Examples:

- `@astichi_insert(A.try1.finally_body, order=10)` for block insertion
- `@astichi_except(A.try1.excepts, ValueError, order=10)` for handler insertion
- `@astichi_elif(A.if1.elifs, cond, order=10)` for elif insertion

## 21. Wild ideas worth not losing

These are intentionally speculative.

### 21.1 Clause objects as composables

Maybe Astichi could have composables whose root semantic unit is not a module
body, but a clause:

- `ExceptComposable`
- `ElifComposable`
- `CaseComposable`

Probably too much surface area, but conceptually neat.

### 21.2 Function wrappers as clause carriers

Use the wrapped Python object as syntax cargo:

- params encode alias names
- decorator args encode header
- body encodes clause body

This may be the least-bad route for `except` and `elif`.

### 21.3 Named target families

Maybe targets could be more semantic:

- `A.try1.handlers`
- `A.try1.finally`
- `A.if1.branches`
- `A.match1.arms`

More readable than raw AST field names.

### 21.4 AST-schema-driven extension system

Potentially overengineered, but maybe:

- generated target compatibility from Python AST schema

This would make Astichi more compiler-like than DSL-like.

### 21.5 Partial grouped clauses

If whole-clause surfaces prove too awkward, a middle ground is grouped partial
holes that must be satisfied together:

- `catch[i].type`
- `catch[i].alias`
- `catch[i].body`

with atomic validation that all parts exist.

Still probably worse than whole-clause inserts, but worth noting as fallback.

## 22. Practical likely order if pursued

If this family is pursued incrementally, a plausible order is:

1. body-only singleton targets
   - `finally_body`
   - `else_body`
2. `elif` clause inserts
3. `except` clause inserts
4. decorator-list targets
5. `with_item` / parameter-entry / similar typed list entries
6. `case` clauses after a dedicated pattern design

## 23. Summary

Most likely good directions:

- keep block insertion for body-only extensions
- add whole-clause supplies for `elif` and `except`
- treat `case` as a separate harder problem
- consider a future typed-list-field abstraction under the hood

Most likely bad direction:

- splitting structured control-flow clauses into separately wired type/body/name
  fragments

That route is likely to create more hygiene and cardinality trouble than it is
worth.
