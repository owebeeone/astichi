# Issue 002: Expression Port Shape Validation Gap

## Status

Resolved.

## Problem

Expression-placement port compatibility is currently too permissive.

The current validator treats all expression placements as mutually compatible,
regardless of sub-shape:

- scalar expression
- positional variadic expression
- named variadic expression

This was acceptable only if a later phase enforced the fine-grained rules. The
current implementation does not yet do that.

## Evidence

- `src/astichi/model/ports.py`
  - `validate_port_pair(...)` only checks shape when placement is not `"expr"`
- `tests/test_model.py`
  - `test_expr_supply_matches_expr_demand_any_sub_shape()` explicitly allows one
    scalar supply to satisfy scalar, positional-variadic, and named-variadic
    demands
- `dev-docs/AstichiApiDesignV1-InsertExpression.md`
  - says finer constraints are enforced later by composition/materialization
- current materialization code does not implement those later constraints

## Impact

Invalid compositions can be accepted without any phase rejecting them.

Examples:

- scalar insert accepted for positional variadic target
- scalar insert accepted for named variadic target
- any expression-shaped supply accepted for any expression-shaped demand

This is a real semantic hole, not just a missing refinement.

## Resolution

Resolved by keeping coarse `"expr"` placement compatibility in the port model
and enforcing fine-grained shape/cardinality rules during build/materialize,
where the target context is known.

Implemented checks now cover:

- scalar target accepts at most one insert
- named variadic target requires dict-display payloads
- block target rejects expression inserts by placement
- expression target rejects non-expression sources

## Resolution Evidence

- `tests/test_expression_insert_pipeline.py`
  - duplicate scalar rejection
  - named variadic non-dict rejection
  - block target rejection
  - decorator insert rejection for expr target
