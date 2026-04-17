# Issue 003: Provenance Format Drift

## Status

Open.

## Priority

Low.

## Problem

The implemented provenance format no longer matches the V1 design documents.

Implementation currently emits a trailing comment:

```python
# astichi-provenance: ...
```

But the V1 design documents still specify:

```python
astichi_provenance_payload("...")
```

## Evidence

- `src/astichi/emit/api.py`
  - uses `PROVENANCE_PREFIX = "# astichi-provenance: "`
  - emits and parses provenance from comments
- `tests/test_emit.py`
  - asserts the comment form
- `dev-docs/AstichiApiDesignV1.md`
  - specifies `astichi_provenance_payload("...")`
- `dev-docs/historical/AstichiV1Milestones.md`
  - specifies the tail call form
- `dev-docs/V1ProgressRegister.md`
  - has drifted to document the comment form instead

## Impact

The repository now has two conflicting contracts:

- code/tests say comment
- main V1 design says payload call

This creates confusion for future implementation and documentation work,
especially around AST-visible round-trip semantics.

## Suggested Resolution

Decide one V1 provenance format and make all documents and code converge.

If the comment form is kept:

1. Update `AstichiApiDesignV1.md`
2. Update `historical/AstichiV1Milestones.md`
3. Add a short note explaining why the original tail-call direction was not kept

If the payload-call form is restored:

1. Change `emit/api.py` to emit `astichi_provenance_payload("...")`
2. Change extraction/verification to parse that call from the AST
3. Update tests to assert the call form

Given current code, the lower-effort path is to document the comment form.
Given earlier design intent, the more semantically faithful path is to restore
the payload-call form.

## Tests Needed

- one authoritative syntax test for the chosen provenance form
- extraction test for the chosen form
- tampered-source round-trip failure test
- missing-payload failure test
- code/doc references should be reviewed together when the decision is made
