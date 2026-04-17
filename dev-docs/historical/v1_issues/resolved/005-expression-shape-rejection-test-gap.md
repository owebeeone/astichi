# Issue 005: Expression Shape Rejection Test Gap

## Status

Resolved.

## Problem

The current tests do not prove that invalid expression-shape combinations are
rejected at the correct phase.

V1 currently distinguishes:

- scalar expression targets
- positional variadic targets
- named variadic targets

But the suite is missing focused negative tests for cases that should fail.

## Evidence

- `tests/test_model.py`
  - currently contains a permissive expression-shape compatibility test
- there are no end-to-end negative tests for:
  - scalar target with multiple inserts
  - named variadic target with non-dict payload
  - positional/named variadic misuse at build/materialize time

## Impact

Without negative tests, invalid compositions may:

- pass silently
- fail too late
- fail in the wrong phase
- fail with unclear errors

That weakens the contract around V1 expression insertion and shape rules.

## Resolution

Added explicit negative tests and corresponding enforcement for the intended
failure phase.

## Resolution Evidence

- `tests/test_expression_insert_pipeline.py`
  - scalar target + two inserts
  - named variadic target + non-dict payload
  - block target + expression insert
  - expression target + decorator insert
