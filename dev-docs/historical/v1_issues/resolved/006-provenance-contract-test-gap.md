# Issue 006: Provenance Contract Test Gap

## Status

Resolved.

## Problem

The provenance tests currently validate the implemented comment format, but they
do not protect the normative V1 contract because the code and design documents
have drifted apart.

This is a separate issue from the format drift itself: even after the format is
chosen, the suite needs one authoritative contract test set for that choice.

## Evidence

- `tests/test_emit.py`
  - asserts the current comment form
- `dev-docs/AstichiApiDesignV1.md`
  - specifies `astichi_provenance_payload("...")`
- `dev-docs/historical/AstichiV1Milestones.md`
  - also specifies the payload-call form

## Impact

The suite can stay green while the repo disagrees about the actual provenance
syntax.

That means future changes can accidentally preserve the wrong behavior simply
because tests only follow the current implementation.

## Resolution

The current implementation contract is now explicitly covered by tests for the
comment-based provenance payload syntax, extraction, and full-pipeline
round-trip behavior.

## Resolution Evidence

- `tests/test_emit.py`
  - exact comment-presence checks
  - single trailing provenance comment check
  - extraction and round-trip validation
  - post-materialize round-trip validation
