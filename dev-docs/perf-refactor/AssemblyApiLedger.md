# Assembly API Ledger

Status: Slice 0 corrective pruning checkpoint.

This ledger is the Slice 0 deliverable. It names the assembly APIs that Astichi
and YIDL actually use before the lower-engine refactor starts deleting or
quarantining obsolete surfaces. The corrective pruning checkpoint removes the
generic assembler client/runner/production adapter because its only callers
were Astichi adapter tests and summary docs; YIDL uses the scope facade
directly.

## Classification Labels

Use one of these labels for each discovered surface:

- `required-hot`: used by the YIDL or Astichi assembly hot path.
- `required-final`: needed to produce final source, AST, executable classes, or
  diagnostics, but not needed during candidate lookup or inventory merge.
- `validation-only`: needed to reject malformed input or explain failures.
- `adapter-only`: temporarily preserved while route-through is staged.
- `removable`: unused after YIDL and Astichi callers are reviewed.

## Ledger Shape

```text
API surface:
  owner module:
  current callers:
  YIDL caller:
  classification:
  replacement:
  removal slice:
  golden coverage:
  bespoke diagnostic coverage:
```

## Audited Surfaces

| API surface | Current callers | YIDL caller | Classification | Replacement | Removal slice | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| `AssemblyScope.add` | `tests/test_assembler_scope.py`, docs snippets | `yidl/src/yidl/generation/assembly_runtime.py` | `required-hot` | lower occurrence append; Slice 6a maintains parallel lower state | keep; make lower state authoritative in Slice 8 | assembler scope tests, YIDL final goldens, structural `scope_lower_occurrence_state` golden |
| `AssemblyScope.apply` | assembler scope tests/docs | `yidl/src/yidl/generation/assembly_runtime.py` | `required-hot` | lower apply over candidate handles and overlays; Slice 6a records parallel lower edges/overlays | keep; route in Slices 9-10 | assembler scope tests, YIDL final goldens, structural `scope_lower_occurrence_state` golden |
| `AssemblyScope.build` | assembler scope tests/docs | `yidl/src/yidl/generation/assembly_runtime.py` | `required-final` | lower-owned materialization facade | keep; route in Slice 11 | final-output goldens |
| `AssemblyScope.inventory` | `find_candidates(scope.inventory, ...)`, inventory tests | `yidl/src/yidl/generation/assembly_runtime.py` | `adapter-only` | direct lower candidate query plus debug projection | decide in Slice 8; remove hot-path use by Slice 13 | structural inventory/snapshot goldens |
| `find_candidates` | assembler scope tests/docs | `yidl/src/yidl/generation/assembly_runtime.py` | `required-hot` | lower index query returning candidate handles | route in Slice 7 | assembler diagnostics tests and structural goldens |
| `require_one` | assembler scope tests/docs | `yidl/src/yidl/generation/assembly_runtime.py` | `validation-only` | lower candidate batch diagnostic formatter | keep until diagnostics migrate | bespoke missing/ambiguous tests |
| `as_composable` | assembler scope tests/docs | `yidl/src/yidl/generation/assembly_runtime.py` | `required-hot` | composable resource descriptor | keep facade; lower in Slice 7 | assembler scope tests |
| `as_external_value` | assembler scope tests/docs | `yidl/src/yidl/generation/assembly_runtime.py` | `required-hot` | external-value resource descriptor with facade object slot | keep facade; lower in Slice 7 | external bind goldens and diagnostics tests |
| `as_identifier` | assembler scope tests/docs | `yidl/src/yidl/generation/assembly_runtime.py` | `required-hot` | identifier resource descriptor | keep facade; lower in Slice 7 | identifier bind goldens and diagnostics tests |
| `BindingCandidate` and concrete candidate classes | `src/astichi/assembler/scope.py`, YIDL type hints | `yidl/src/yidl/generation/assembly_runtime.py` imports `BindingCandidate` from `astichi.assembler.scope` | `adapter-only` | opaque lower candidate handle plus diagnostic view | remove from YIDL-facing hot path by Slice 13 | bespoke unsupported/ambiguous candidate diagnostics |
| `BindingResource`, `DemandSelector`, and concrete resource classes | `src/astichi/assembler/scope.py`, assembler scope tests | no top-level YIDL import; resources created through helpers | `adapter-only` | registered resource descriptors and selector objects | remove or make private after Slice 7 | assembler scope tests |
| top-level exports of candidate/resource implementation classes from `astichi.assembler` | docs snippet type annotation and one bespoke test | none | `removable` | import low-level test-only types from `astichi.assembler.scope`; keep public top-level helpers only | removed in Slice 0 | assembler scope test adjusted |
| `code_owner_parts` top-level export | none outside `scope.py` | none | `removable` | private helper inside candidate matching | removed in Slice 0 | covered by owner-match tests |
| `astichi.assembler.client` and `BuildIndex` | deleted generic adapter implementation/tests only | none | `removable` | direct `AssemblyScope` facade used by YIDL | removed in corrective Slice 0 | adapter tests removed; YIDL final goldens carry success path |
| `AssemblyRunner` and `astichi.assembler.runner` | deleted generic adapter implementation/tests only | none | `removable` | direct YIDL scope orchestration | removed in corrective Slice 0 | adapter tests removed; assembler scope tests cover remaining mechanics |
| `astichi.assembler.production` generic production specs | deleted generic adapter implementation/tests only | none | `removable` | YIDL-owned production orchestration over scope API | removed in corrective Slice 0 | adapter tests removed; YIDL final goldens carry success path |
| `astichi.compile` | package users, tests, docs, YIDL generators | `yidl/src/yidl/generation/*.py` | `required-hot` | lower-backed composable facade; Slices 5a/5b store internal lower template metadata and import it into shared lower engines | continue route-through in Slice 6 | compile/final-output goldens plus structural `compile_template_metadata` and `shared_template_registration` goldens |
| `astichi.compile(file_name=...)` | tests/data/gold_src, docs | YIDL generated source helpers may pass provenance | `required-final` | lower source locator metadata | keep | location/provenance goldens |
| `astichi.compile(line_number=...)` | tests and diagnostics fixtures | no direct YIDL hot-path call found | `required-final` | lower source locator metadata | keep | location diagnostics tests |
| `astichi.compile(offset=...)` | tests/docs | no direct YIDL hot-path call found | `required-final` | lower source locator metadata | keep | provenance/location tests |
| `astichi.compile(arg_names=...)` | tests/data/gold_src and docs | YIDL uses identifier binding paths instead | `validation-only` | identifier demand registration metadata | keep while supported public keyword | identifier-bind diagnostics |
| `astichi.compile(keep_names=...)` | tests/data/gold_src, docs, YIDL matcher/data schema via `.with_keep_names(...)` | YIDL uses `.with_keep_names(...)` | `required-final` | lower hygiene stream | keep; lower in Slice 12c | hygiene goldens |
| `astichi.compile(source_kind=...)` | emitted-source round-trip tests | no YIDL hot-path call found | `validation-only` | source-kind semantic object at registration | keep | emitted-source diagnostics |
| `BasicComposable.bind` | materialize tests/docs | `yidl/src/yidl/generation/assembly_runtime.py` calls bind indirectly through scope external applies | `adapter-only` | lower external overlay | route in Slice 10 | external bind goldens |
| `BasicComposable.bind_identifier` | tests/docs and YIDL generator helpers | `yidl/src/yidl/generation/matcher.py`, `data_schema.py`, `assembly_runtime.py` | `adapter-only` | lower identifier overlay | route in Slice 10 | identifier bind goldens |
| `BasicComposable.with_keep_names` | tests/docs and YIDL helpers | `yidl/src/yidl/generation/matcher.py`, `data_schema.py` | `required-final` | lower hygiene keep-name operation | route in Slice 12c | hygiene goldens |
| builder graph mutation helpers | builder, assembler scope, runner | through `AssemblyScope` only | `adapter-only` | lower state append/apply/materialize | remove hot-path use by Slice 13 | builder and assembler tests |
| `Inventory.__str__` / debug inventory printing | tests/docs | none found | `adapter-only` | structural snapshots and debug views | keep as slow projection only | existing inventory string tests until replaced |
| `Inventory.find_resource` and record-id map accessors | descriptor/inventory tests/docs | none found | `adapter-only` | lower indexes plus structural snapshots | migrate after Slice 7 | inventory tests, then structural goldens |
| parameter-hole helpers | materialize/lowering/tests | YIDL lifecycle-shaped templates | `required-final` | lower materialization operation | route in Slice 12a | parameter goldens |
| funcargs payload helpers | materialize/lowering/tests | YIDL call argument paths | `required-final` | lower materialization operation | route in Slice 12a/12b as needed | funcargs goldens |
| pyimport helpers | materialize/lowering/tests | YIDL generation helpers | `required-final` | lower managed import/hygiene operation | route in Slice 12b | pyimport goldens |
| boundary pass/import/export helpers | materialize/lowering/tests | YIDL generated templates | `required-final` | lower boundary/hygiene stream | route in Slice 12c | boundary goldens |
| keep-name and hygiene helpers | materialize/hygiene/tests | YIDL generator helpers | `required-final` | lower `hygiene_stream` | route in Slice 12c | hygiene goldens |

Audit scope included Astichi implementation/tests/docs, `tests/data/gold_src/`,
and YIDL generation/runtime callers under `yidl/src/yidl/generation`.

## Exit Gate

Slice 0 is complete only when every audited surface has a classification, a
replacement/removal decision, and golden or diagnostic coverage notes. Lower
engine code should not depend on an API that this ledger marks removable.
