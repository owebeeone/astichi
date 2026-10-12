# Localized native composable handoff result

Status: implemented and owner-verified on the focused fix branch; unpublished.

Scope and original operator authority are recorded in `StructuralHandoffTask.md`.
Baseline: `1c47f781d3804130fdd61cbee07a3b2e4529158a`. The stopped SDK detour,
including partial native implementation, is preserved at
`6203814babe0400deac204a71f6fa5e45b9efb4f` on
`archive/dataclass-sdk-detour`. Its raw uncommitted evidence was separately
copied, hash-verified and moved outside the active checkout. No detour work was
cherry-picked into this fix. YIDL and Dataclass source were not changed.

## Change and behavior

Native specialization now copies an already registered native template into its
temporary engine and registers the transformed native tree through the existing
metadata extractors. It does not reparse the emitted source for that handoff.
Source rendering remains for existing template identity and public emission.
Native implementation diff: **83 added + 9 deleted = 92 changed lines**, including
formatting, below the operator's 100-line ceiling; Python glue, tests and docs are
separate. No public package API, persistence facility or dependency upgrade.

Each resulting binding owns its saved native engine, so temporary engine closure
cannot invalidate it and specialization does not accumulate saved templates in a
global registry. Source and destination ownership/closed-state checks remain
active. Working trees are cloned; published composables remain unchanged.

The operator clarified that existing nodes' diagnostic locations must refer to
their original source. The first probe used original offsets with newly rendered
text and wrongly expected reparsed-coordinate parity; it was rejected. The fix
keeps the original location source paired with the retained offsets. The baseline
lost a hole's line ten location and reported line one after two bindings; the
regression now retains all four original line/column attributes. This intentional
diagnostic correction replaces the earlier assumption of exact legacy snapshot
parity; generated program text, bindings and source-based identity are checked
separately.

Generic Python-AST rebuilding, authored-source compilation, older native-extension
compatibility and arbitrary cross-source composition retain their existing paths.
This is not a claim that every Astichi source round trip has been removed.

## Verification

- Baseline release build on Windows: focused specialization and canonical
  generated-source golden suite, **96 passed**.
- Genuine baseline regression: original-location assertion fails, line one versus
  authored line ten. No import/setup failure was used as the behavioral RED.
- Corrected focused suite on Windows: **14 passed**, covering original coordinates,
  emitted identity, immutable originals, successive bindings, absence of source
  registration, and rejection of wrong-owner/closed-source template copies.
- Full dual-backend suite on macOS, CPython 3.14.3: **2,648 passed, 14 skipped**.
- Full Windows suite before the final ownership-test addition: **2,644 passed,
  14 skipped, 2 failed**. Both failures independently reproduce on the original
  baseline: a test expects forward slashes where Windows `Path` uses backslashes.
  They are not handoff regressions; no unrelated test-harness fix was made.
- Release native builds succeed on Windows x64 and macOS ARM64. Rustfmt, Python
  syntax and diff-whitespace checks pass. No release/wheel publication or full
  supported-Python-version matrix is claimed.

Raw build, RED/GREEN, full-suite and timing evidence resides under the ignored
`scratch/structural-handoff/` directory; timings are not unit-test assertions.

## Measurements

Both snapshots were measured in isolated directories on the same remote Windows
11 x64 host, CPython 3.14.7, Rust release builds and unchanged sibling YIDL sources.
One warm-up per variant was discarded; trial order alternated. These are
single-workload observations, not universal performance claims.

| Native workload | Baseline median | Fix median | Observation |
| --- | ---: | ---: | --- |
| YIDL split dataclass generation, 9 pairs | 277.84 ms | 276.12 ms | 0.62% lower; ranges overlap, no established improvement |
| 100 two-step identifier bindings, 9 pairs | 367.87 ms | 282.20 ms | 23.29% less time; ranges do not overlap |

YIDL generation ranges were 275.19–281.20 ms and 275.03–277.26 ms. Binding ranges
were 365.91–373.17 ms and 278.22–289.24 ms. Every YIDL trial recorded **zero** calls
to native reprojection, native specialization sessions and generic composable
rebuild, explaining why this workload shows no meaningful generation speedup.

Five Python-backend control pairs were also unchanged within variation:
generation medians 461.80 versus 462.97 ms; binding medians 110.38 versus
110.19 ms. Generation phase totals exclude interpreter startup. Native allocation
and peak memory were not measured.

Reproduce with `docs/validation/perf/composable_handoff_compare.py`, supplying
baseline/candidate Astichi roots with matching sibling YIDL snapshots, dependencies
and release native builds. Keep raw comparison JSON in scratch.
