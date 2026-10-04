# Issue 001: Expression Insert Materialization Gap

## Status

Resolved.

## Problem

Expression-form inserts are recognized and modeled, but they are not applied by
the current build/materialize pipeline.

The current implementation supports:

- lowering recognition of `astichi_insert(target, expr)`
- supply-port extraction for expression inserts
- hygiene boundary handling for expression inserts

But the actual merge/materialize path only splices block-position holes.

## Evidence

- `src/astichi/materialize/api.py`
  - `build_merge(...)` only replaces block holes by copying source module bodies
    into `_replace_holes_in_body(...)`
  - `_extract_hole_name(...)` only recognizes `astichi_hole(...)` used as a
    standalone expression statement
- `src/astichi/lowering/markers.py`
  - expression-form `astichi_insert(target, expr)` is recognized
- `src/astichi/model/ports.py`
  - expression-form `astichi_insert(...)` produces a supply port
- `src/astichi/hygiene/api.py`
  - expression-form `astichi_insert(...)` creates a fresh hygiene boundary

## Impact

V1 currently claims more expression-insert capability than the executable build
path actually provides.

This creates a bad failure mode:

- expression insert syntax parses successfully
- the composable advertises the insert as supply
- but no actual AST substitution happens during build/materialize

So the feature appears supported but is semantically incomplete.

## Resolution

Implemented with a two-phase model:

1. `build()` resolves edges and replaces expression holes with surviving
   `astichi_insert(...)` wrappers in the target AST.
2. `materialize()` applies hygiene while those wrappers are still present, then
   unwraps/expands them into final Python AST.

Current supported behavior:

- scalar expression target: exactly one insert
- positional variadic target: ordered expansion
- named variadic target: ordered dict-display expansion
- dict literal `**` expansion: ordered dict-entry expansion

Unsupported combinations now fail explicitly.

## Resolution Evidence

- `tests/test_expression_insert_pipeline.py`
  - scalar expression insertion
  - positional variadic insertion
  - named variadic insertion
  - dict-entry expansion
  - scalar duplicate rejection
