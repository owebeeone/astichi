# Issue 004: Expression Insert End-to-End Test Gap

## Status

Resolved.

## Problem

The test suite exercises expression inserts in lowering, port extraction, and
hygiene, but not in the actual `build()` / `materialize()` execution path.

This is a distinct issue because V1 semantics depend on what happens when an
inserted expression is finally spliced into its target, not just on whether the
marker is recognized.

## Evidence

- `tests/test_lowering_shapes.py`
  - covers recognition and shape inference for expression-form
    `astichi_insert(...)`
- `tests/test_model.py`
  - covers supply-port extraction for expression inserts
- `tests/test_hygiene.py`
  - covers scope-boundary and renaming behavior for expression inserts
- `tests/test_build_merge.py`
  - only covers block-hole replacement
- `tests/test_materialize.py`
  - only covers block-hole composition and block-wrapper hygiene

## Impact

The highest-risk expression-insert behavior is currently unverified:

- scalar substitution
- variadic positional insertion
- variadic named insertion
- ordering across multiple inserts
- error behavior for unsupported combinations

This makes it easy for the implementation to drift while the suite stays green.

## Resolution

Added a dedicated end-to-end test module covering build/materialize behavior for
expression inserts.

## Resolution Evidence

- `tests/test_expression_insert_pipeline.py`
  - scalar expression insertion
  - positional variadic insertion ordering
  - named variadic insertion ordering
  - dict-entry insertion
  - expression-insert hygiene through materialize
