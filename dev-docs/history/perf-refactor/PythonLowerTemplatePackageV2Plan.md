# Python Lower Template Package V2 Plan

Status: roll-build plan required before native N9b3.

The native lower engine cannot complete managed imports and hygiene until the
Python lower engine exposes the same behavior-complete lower-template package
that native will later produce. This plan upgrades the Python reference engine
first so native has a stable oracle and API target.

## Goal

Move all materialization/hygiene facts currently held in Python-only
`BasicComposable` side channels into `LowerTemplatePackageV2` and make Python
materialization-plan construction consume only lower-engine package/state APIs.

Current side channels to remove from planning:

- `AssemblyScope._lower_composable_by_occurrence` for hygiene decisions;
- `BasicComposable.markers` for strip/keep/managed-import stream construction;
- `BasicComposable.classification.locals` for rename-if-collides decisions;
- ad hoc source AST walks during materialization-plan construction.

Python may still use Python ASTs to build final artifacts until native
materialization catches up. The boundary change is about plan construction and
lower metadata ownership.

## Target Modules

Likely Python files:

- `src/astichi/lower_engine/package_v2.py`: package row containers, interning,
  path tables, package snapshot projection.
- `src/astichi/lower_engine/package_extract.py`: Python extraction from
  existing `BasicComposable` facts and AST/name-analysis helpers.
- `src/astichi/lower_engine/templates.py`: attach package handles/rows to
  templates without breaking existing record/locator users.
- `src/astichi/lower_engine/engine.py`: register package data and expose package
  accessors.
- `src/astichi/lower_engine/materialization.py`: build hygiene streams from
  package/state rows.
- `src/astichi/assembler/scope.py`: stop planning hygiene from composable side
  channels; keep artifact materialization AST paths until native artifact
  builder replaces them.

## P0: Package Schema Skeleton

Goal: introduce the Python data model without changing behavior.

Work:

- add `LowerTemplatePackageV2` containers with interned string, path, and
  AST-path tables;
- add row tables for locators, records, scopes, and binding sets;
- add deterministic package snapshot projection for goldens;
- add lightweight derived indexes over row ids, but keep them out of snapshots;
- pin the v2/v1 source-of-truth policy: v2 package rows are canonical and v1
  structural snapshots are renderers over populated v2 rows, not an independent
  extraction path;
- pin the intern policy: interns are per-package, ids are assigned in
  deterministic extraction order, snapshots render strings/paths rather than
  intern ids, and no inter-package id reuse is allowed in v1.

Acceptance:

- package containers round-trip through canonical JSON projection;
- empty/package-minimal fixtures have stable snapshots;
- v1 structural snapshot projection for populated row classes is derived from
  package rows;
- no materialization behavior changes.

## P1: Records And Locators Mirror Existing Templates

Goal: make package rows reproduce the current structural inventory record and
locator data.

Work:

- populate package locator rows from existing `SourceLocator` data;
- populate package record rows from existing `TemplateRecordSpec` /
  `TemplateRecord` data;
- map surface and operation keys to registered ids while preserving stable debug
  keys in snapshots;
- store package on `LowerTemplateBinding` and registered lower templates.

Acceptance:

- package record/locator projections match current structural snapshot content;
- v1 structural snapshot writer reads record/locator facts from package rows;
- existing structural inventory goldens stay unchanged;
- native snapshot import remains compatible during the transition.

## P2a: Scope Row Schema And Discovery

Goal: add scope rows and discover lexical scope structure without binding-set
parity yet.

Work:

- add `ScopeRow` storage and snapshot projection;
- extract module/function/async-function/class scope rows;
- record owner paths and AST paths for scopes;
- assign deterministic `scope_id` and `parent_scope_id` values;
- connect records and markers added later to the owning scope id where the
  information is already available.

Acceptance:

- package goldens cover nested module, class, function, and async-function
  scopes;
- record/locator projections remain unchanged;
- no materialization behavior changes.

## P2b: Local And Argument Binding Extraction

Goal: populate scope binding sets from the same facts Python hygiene currently
computes with AST walkers and classification.

Work:

- record local binding sets for assignment, delete targets, imports,
  function/class definitions, and other current binders;
- record argument binding sets for function and async-function scopes;
- preserve sorted deterministic set ids in snapshots;
- match current `_lower_scope_binding_names(...)` behavior on existing fixtures;
- if package extraction finds a binding the helper misses on a fixture, update
  the helper to match the package and add a regression test rather than making
  the package bug-compatible with the helper.

Acceptance:

- package goldens cover module-level pyimport collisions, function body
  collisions, class/function definitions, imports, assignments, deletes, and
  function arguments;
- package-derived binding sets match current Python helper output for covered
  fixtures;
- no materialization behavior changes.

## P2c: Package Binding Helpers And Indexes

Goal: expose package-derived binding helpers for later planner migration.

Work:

- add derived indexes for bindings by scope id and owner path;
- add helper APIs that return the current boundary and pyimport collision
  binding views from package rows;
- keep indexes out of package snapshots.

Acceptance:

- helper tests prove package-derived binding views match existing helper output;
- derived indexes rebuild deterministically from package rows;
- no materialization behavior changes.

## P3a: Marker Row Schema And Source Ordering

Goal: add marker rows and deterministic marker ordering without full marker
coverage yet.

Work:

- add `MarkerRow` storage and snapshot projection;
- assign deterministic source order across nested scopes;
- include scope id, owner path id, AST path id, statement path id, resource name
  id, operation id, and common flags;
- add derived marker indexes by kind and scope.

Acceptance:

- package goldens cover basic marker ordering across module/function/class
  nesting;
- marker indexes rebuild deterministically from package rows;
- no materialization behavior changes.

## P3b: Boundary Marker Rows And Flags

Goal: canonicalize the marker facts required by boundary hygiene.

Work:

- extract marker rows for `astichi_import`, `astichi_export`, and
  `astichi_pass`;
- preserve explicit-bind and outer-bind flags;
- connect marker rows to owning scopes and owner paths;
- expose package helpers equivalent to the current boundary marker support
  checks.

Acceptance:

- package goldens cover import/export/pass boundary markers, including explicit
  and outer bind forms;
- package-derived boundary marker helper output matches current Python helper
  behavior;
- no materialization behavior changes.

## P3c1: Keep And Pyimport Marker Rows

Goal: cover the simplest remaining direct-call marker families.

Work:

- extract marker rows for `astichi_keep` and `astichi_pyimport`;
- record typed marker columns/flags needed by current behavior;
- keep arbitrary captures out of runtime rows; use typed columns/flags and only
  render debug captures in snapshots.

Acceptance:

- package goldens cover keep markers and pyimport markers that do not produce
  inventory records;
- package-derived marker rows replace direct `BasicComposable.markers` reads in
  tests for keep/pyimport marker enumeration;
- no materialization behavior changes.

## P3c2: Comment Marker Rows

Goal: canonicalize comment marker rows separately from behavior-bearing
markers.

Work:

- extract marker rows for `astichi_comment`;
- record preserve/strip policy data needed by materialization debug projections;
- keep comment marker handling independent from managed-import and boundary
  marker helpers.

Acceptance:

- package goldens cover comment marker ordering and marker-only syntax;
- no materialization behavior changes.

## P3c3: Ref And Ref-Sentinel Marker Rows

Goal: canonicalize ref markers, including sentinel-attribute forms that may need
richer row data.

Work:

- extract marker rows for `astichi_ref(...)` value forms;
- extract marker rows for sentinel-attribute ref forms such as store/delete
  compatible refs;
- record context data needed to distinguish load/store/delete behavior;
- add a typed side row if the flat marker row cannot represent the context
  without arbitrary captures.

Acceptance:

- package goldens cover ref value and ref-sentinel forms;
- row validation rejects unsupported ref contexts with focused diagnostics;
- no materialization behavior changes.

## P3c4: Unroll Marker Rows

Goal: canonicalize statement-context unroll markers separately from call-marker
families.

Work:

- extract marker rows for supported unroll markers;
- record loop-domain and statement-context facts needed by later native
  materialization;
- keep unroll binding/scope rules explicit rather than reusing call-marker
  assumptions.

Acceptance:

- package goldens cover supported unroll marker shapes;
- unsupported unroll shapes remain covered by focused diagnostics;
- no materialization behavior changes.

## P4: Managed Import Rows

Goal: normalize managed import requests into package rows.

Work:

- derive managed import rows from pyimport marker rows added in P3c1;
- record module path id, final local name id, original symbol id, source order,
  scope id, and import flags;
- match current `collect_managed_imports(...)` behavior.

Acceptance:

- package goldens cover `module=foo, names=(a, b)`, `module=foo.bar`,
  `as_=...`, duplicate requests, and collision cases;
- package-derived managed import rows match current Python managed import
  records for covered fixtures.

## P5a: Unresolved Gate, Strip, And Keep Hygiene From Package Rows

Goal: migrate the simplest hygiene operations to package/state planning.

Work:

- move keep-name hygiene construction into lower-engine package/state planning;
- move strip-marker hygiene construction into lower-engine package/state
  planning;
- explicitly enumerate unresolved-gate inputs:
  `gate_no_unresolved` reads live/dead/satisfied state from `AssemblyState` and
  unresolved-capable records from package record rows; it does not read marker
  or managed-import rows in this slice;
- if a future gate variant needs marker or managed-import rows, add that gate
  as its own slice with named package/state inputs;
- keep operation-stream edge/overlay behavior unchanged;

Acceptance:

- existing materialization-plan structural goldens for keep/strip/gate cases
  pass;
- planner no longer reads `BasicComposable.markers` for keep/strip operations.

## P5b: Managed Import Hygiene From Package Rows

Goal: migrate pyimport request hygiene and pyimport collision detection.

Work:

- move managed-import request hygiene construction into package/state planning;
- move pyimport collision rename hygiene into package/state planning;
- match current `collect_managed_imports(...)` and collision ordering.

Acceptance:

- existing materialization-plan structural goldens for pyimport request and
  pyimport collision cases pass;
- planner no longer reads `BasicComposable.markers` for managed import
  operations.

## P5c: Boundary Collision Hygiene From Package Rows

Goal: migrate boundary collision and rename-if-collides planning.

Work:

- move boundary marker hygiene construction into package/state planning;
- move source-local collision detection from `source.classification.locals` to
  package scope/binding rows;
- preserve existing deterministic hygiene ordering.

Acceptance:

- existing materialization-plan structural goldens for boundary marker,
  keep-collision, and boundary-elif cases pass;
- planner no longer reads `BasicComposable.classification` for hygiene.

## P5d: Remove Planner Side-Channel Reads And Add Guards

Goal: enforce the new planning boundary.

Work:

- remove remaining materialization-plan construction reads from
  `AssemblyScope._lower_composable_by_occurrence`;
- add static guard tests that assert lower-engine materialization modules and
  plan-construction paths do not import or reference `BasicComposable`,
  `markers`, or `classification` for planning;
- add runtime package-only mode for the structural materialization-plan golden
  suite: plan construction receives package/state handles only, and the
  composable side-channel attributes are absent or inaccessible;
- keep artifact materialization free to use Python ASTs until native artifact
  building replaces it.

Acceptance:

- full materialization-plan structural golden suite passes;
- static guard tests catch module-boundary regressions;
- runtime package-only tests catch dynamic attribute and indirect helper
  regressions;
- counters still distinguish planning from artifact materialization.

## P6: Facade Cleanup And Compatibility Gate

Goal: make v2 package ownership explicit and remove transition ambiguity.

Work:

- make `LowerTemplateBinding` carry the package as the authoritative lower
  metadata payload;
- keep current v1 structural snapshot projection as debug/golden output, derived
  from package rows rather than recomputed independently;
- add a capability/feature flag for package-v2-enabled lower engines;
- update native detailed plan so N9b3 consumes package rows, not snapshots or
  Python side-channel metadata.

Acceptance:

- package-v2 path is the default Python lower-engine path;
- Python lower-engine capabilities advertise `python.lower_template_package_v2.v1`
  and `python.materialization_plan.package_only.v1`;
- native selection continues to be gated until native advertises
  `native.lower_template_package_v2.v1` in addition to the full lower-engine
  capability;
- docs and tests name the package as the materialization/hygiene contract.

## Native Parallel Work During Python V2

Native N9b3 is blocked until P5d because it depends on the finalized package
contract and Python package-only materialization planner. Native work is not
fully blocked:

- package-independent native slices already completed or allowed before P5d:
  N9a operation streams and N9b1 overlay/gate streams;
- native may continue implementation that consumes records, locators, edges,
  overlays, or artifact-copy primitives without marker/scope package rows;
- native must not implement parallel marker/scope/managed-import extraction
  against an in-progress schema except as throwaway spike code.

## Golden Strategy

Add a package golden phase or a package subdirectory under structural goldens.
Use package projections for success-path fixtures:

- simple expression hole;
- block insertion with boundary markers;
- parameter insertion;
- funcargs insertion with directive placeholders;
- identifier and external overlays;
- pyimport request and pyimport collision;
- keep-name collision;
- boundary elif.

Bespoke tests should be limited to parser/recognition errors, row validation,
and narrow edge cases that goldens cannot express cleanly.

## Roll-Build Tags

Suggested tag prefix:

```text
perf-refactor/python-v2-package-p0
perf-refactor/python-v2-package-p1
perf-refactor/python-v2-package-p2a
perf-refactor/python-v2-package-p2b
perf-refactor/python-v2-package-p2c
perf-refactor/python-v2-package-p3a
perf-refactor/python-v2-package-p3b
perf-refactor/python-v2-package-p3c1
perf-refactor/python-v2-package-p3c2
perf-refactor/python-v2-package-p3c3
perf-refactor/python-v2-package-p3c4
perf-refactor/python-v2-package-p4
perf-refactor/python-v2-package-p5a
perf-refactor/python-v2-package-p5b
perf-refactor/python-v2-package-p5c
perf-refactor/python-v2-package-p5d
perf-refactor/python-v2-package-p6
```

Do not proceed to native N9b3 until P5d is green. P6 can run before or
alongside native N9b3 if the package contract and planner behavior are already
stable.
