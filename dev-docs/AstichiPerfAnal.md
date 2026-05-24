# Astichi Perf Analysis: YIDL Lifecycle Import Path

Status: current analysis.

This note captures the current hot path exposed by the YIDL lifecycle decorator
while importing Pyrolyze's LCM context implementation. It is intentionally
measurement-heavy: the next Astichi performance work needs to reduce the
runtime generation path from seconds to the sub-millisecond range, and that
requires understanding both the obvious hotspots and the second-order effects
that appear after the first hotspot is removed.

## Summary

The current representative workload is importing:

```bash
python -c 'import pyrolyze.runtime.context_lcm'
```

with the parent checkout source roots on `PYTHONPATH`.

That import decorates 8 lifecycle state classes. After switching
`yidl_lifecycle.lifecycle` from source-string `exec()` to direct executable AST
`compile(..., "exec")`, the wall-clock split is:

| Phase | 8 classes | Per class | Notes |
| --- | ---: | ---: | --- |
| Harvest lifecycle facts | 0.002 s | 0.0003 s | Not a problem |
| YIDL/Astichi assembly | 4.597 s | 0.575 s | Dominant cost |
| Materialize to executable AST | 0.660 s | 0.083 s | Second-order cost |
| Compile and exec AST | 0.009 s | 0.001 s | Already near target |
| Call `build_lifecycle_class` | 0.000 s | 0.000 s | Not measurable |
| **Total decorator work** | **5.268 s** | **0.659 s** | Before unrelated imports |

The high-order conclusion is clear:

- class harvesting is effectively free;
- final class construction is effectively free;
- direct AST execution removed the source `exec()` round trip as a concern;
- **assembly is the current bottleneck**;
- materialization becomes the next bottleneck once assembly is improved.

The sub-1ms target cannot be reached by optimizing Python `exec()`. The
assembly/materialization path must either become hundreds of times faster or be
avoided on the runtime decorator path by caching/pre-generation.

## Reproducing The Numbers

Run these commands from the parent checkout root.

Set the source path once:

```bash
export PYTHONPATH="astichi/src:grip-py/src:grip-py-demo/src:grip-pyrolyze/src:grip-pyrolyze-examples/src:huggy/src:pyrolyze/src:yidl/src:yidl-lifecycle/src"
```

### Baseline Import Time

Measure a single package import. This avoids the direct-file execution trap
where `context_lcm.py` is executed once as `pyrolyze.runtime.context_lcm` and
again as `__main__`.

```bash
/usr/bin/time -p .venv/bin/python -c 'import pyrolyze.runtime.context_lcm'
```

Current observed result:

```text
real 5.72
user 5.65
sys  0.03
```

For comparison, running the file directly can roughly double the work:

```bash
/usr/bin/time -p .venv/bin/python pyrolyze/src/pyrolyze/runtime/context_lcm.py
```

The direct-file path imports `pyrolyze.runtime`, whose `__init__.py` eagerly
imports `pyrolyze.runtime.context`, which defaults to `context_lcm`.

### Phase Timer

This measures the decorator phases directly without profiler overhead.

```bash
.venv/bin/python - <<'PY'
from __future__ import annotations

from collections import defaultdict
import time

import yidl_lifecycle.lifecycle as lifecycle_module

rows = []
totals = defaultdict(float)


def timed_lifecycle(cls: type[object]) -> type[object]:
    row = {"class": f"{cls.__module__}.{cls.__qualname__}"}

    start = time.perf_counter()
    harvested = lifecycle_module.harvest_lifecycle_definition(cls)
    row["harvest"] = time.perf_counter() - start

    start = time.perf_counter()
    composable = lifecycle_module._build_lifecycle_composable(harvested)
    row["assembly"] = time.perf_counter() - start

    start = time.perf_counter()
    module_ast = composable.to_executable_ast()
    row["materialize_ast"] = time.perf_counter() - start

    namespace = {"__name__": cls.__module__}
    start = time.perf_counter()
    code = compile(
        module_ast,
        f"<timed.{cls.__module__}.{cls.__qualname__}>",
        "exec",
        dont_inherit=True,
    )
    exec(code, namespace)
    row["compile_exec_ast"] = time.perf_counter() - start

    start = time.perf_counter()
    generated = namespace["build_lifecycle_class"](
        cls,
        **dict(harvested.build_kwargs),
    )
    row["build_class"] = time.perf_counter() - start

    row["total"] = sum(value for key, value in row.items() if key != "class")
    rows.append(row)
    for key, value in row.items():
        if key != "class":
            totals[key] += value
    return generated


lifecycle_module.lifecycle = timed_lifecycle
started = time.perf_counter()
import pyrolyze.runtime.context_lcm  # noqa: F401
elapsed = time.perf_counter() - started

for row in rows:
    print(
        f"{row['total']:.3f}s total | "
        f"assembly={row['assembly']:.3f}s "
        f"materialize={row['materialize_ast']:.3f}s "
        f"exec={row['compile_exec_ast']:.3f}s "
        f"build={row['build_class']:.3f}s "
        f"harvest={row['harvest']:.3f}s | "
        f"{row['class']}"
    )

print("--- totals ---")
for key in (
    "harvest",
    "assembly",
    "materialize_ast",
    "compile_exec_ast",
    "build_class",
    "total",
):
    print(f"{key}: {totals[key]:.3f}s")
print(f"import wall: {elapsed:.3f}s")
PY
```

Current observed totals:

```text
harvest:          0.002s
assembly:         4.597s
materialize_ast:  0.660s
compile_exec_ast: 0.009s
build_class:      0.000s
total:            5.268s
import wall:      5.351s
```

### cProfile

Use cProfile for call counts and relative hotspots. Do not treat absolute
cProfile seconds as wall-clock seconds; this workload measured about 5.35s
without cProfile and 17.88s with cProfile.

```bash
mkdir -p astichi/scratch/perf
.venv/bin/python - <<'PY'
import cProfile

cProfile.run(
    "import pyrolyze.runtime.context_lcm",
    "astichi/scratch/perf/context_lcm_ast_import.prof",
)
PY
```

Inspect the profile:

```bash
.venv/bin/python - <<'PY'
import pstats

stats = pstats.Stats("astichi/scratch/perf/context_lcm_ast_import.prof")
stats.strip_dirs().sort_stats("cumtime").print_stats(45)

print("--- scope.apply callers/callees ---")
stats.print_callers(r"scope.py:256\(apply\)")
stats.print_callees(r"scope.py:256\(apply\)")

print("--- bind_identifier callers/callees ---")
stats.print_callers(r"basic.py:182\(bind_identifier\)")
stats.print_callees(r"basic.py:182\(bind_identifier\)")

print("--- materialize_composable callers/callees ---")
stats.print_callers(r"api.py:3294\(materialize_composable\)")
stats.print_callees(r"api.py:3294\(materialize_composable\)")
PY
```

Current cProfile headline:

```text
118,265,197 function calls
107,621,586 primitive calls
17.882 cProfile seconds
```

## Hotspots

### 1. `AssemblyScope.apply`

The top-level assembly path is:

```text
run_assembly
  _run_production_edges
    _run_edge
      _apply_contribution
        _apply_resource_to_target
          scope.apply(composable)
        _apply_bindings
          scope.apply(external or identifier)
```

For the 8 lifecycle classes:

```text
scope.apply calls: 1597

560  composable applications
421  external value bindings
616  identifier bindings
```

The binding applications are the largest practical hotspot. They mutate one
small thing at a time, but each mutation rebuilds a full composable view.

### 2. Identifier Binding Rebuilds

`BasicComposable.bind_identifier()` is called 616 times.

Each call currently:

1. clones the whole AST;
2. resolves arg identifiers;
3. resolves boundary imports;
4. resolves boundary passes;
5. rebuilds the composable;
6. re-runs marker recognition;
7. re-runs hygiene/name analysis;
8. extracts demand/supply ports;
9. rebuilds inventory.

cProfile for `bind_identifier()`:

```text
616 calls, 5.471 cProfile seconds

_resolve_arg_identifiers:  0.414s
_resolve_boundary_imports: 0.899s
_resolve_boundary_passes:  0.470s
clone_ast:                 0.848s
_rebuild_composable:       2.824s
```

`_rebuild_composable()` is itself broad:

```text
1037 calls, 3.210 cProfile seconds

recognize_markers: 0.738s
analyze_names:     1.035s
build_inventory:   1.291s
ports extraction:  0.131s
```

This is the first optimization target because it is both hot and structurally
avoidable. Applying 3-8 edge-local binds one at a time should be replaced by
per-owner batched binding.

### 3. Target-Site Validation Repeated Scans

Composable adds validate target sites through `_validate_registered_target_site`.

For this workload:

```text
560 calls, 3.976 cProfile seconds
```

Each call recomputes or rescans owner body metadata:

```text
_registered_shell_index:          1.095s
collect_hole_names_in_body:       0.953s
collect_elif_target_names_in_body:0.964s
collect_param_hole_names_in_body: 0.960s
```

This metadata is a natural cache:

- shell index for a registered owner composable;
- hole names;
- elif target names;
- parameter hole names.

The cache must be invalidated when an owner composable is replaced by an
external or identifier binding.

### 4. Occurrence Inventory Replacement

`AssemblyScope._replace_occurrence_inventory()` is called 1605 times.

cProfile split:

```text
1605 calls, 2.325 cProfile seconds

_prefixed_occurrence_inventory: 1.116s
_without_record_ids:           0.463s
Inventory.freeze:              0.491s
add_existing_record:           0.232s
```

This is less hot than binding but still material. The current approach
rebuilds and freezes immutable inventory views after many small mutations.
For fast assembly we probably need a mutable construction inventory with stable
query semantics and a final freeze boundary.

### 5. Materialization

Materialization is not the first hotspot, but after assembly improves it becomes
visible immediately:

```text
to_executable_ast/materialize_composable:
8 calls, 0.660 real seconds
~82 ms per class
```

cProfile shows this includes:

```text
materialize_composable:             2.311s
assign_scope_identity:              0.302s
collect_materialize_gate_facts:     0.219s
recognize_markers:                  0.255s
external_ref lowering:              0.133s
normalize defaulted block holes:    0.135s
resolve boundary imports/passes:    0.167s
clone_ast:                          0.119s
```

If the target is below 1ms, an 82ms materialize step is too slow even after
assembly is fixed. Either materialization must become much faster, or the
runtime path must use a cached executable AST/module.

## Why The Current Shape Is Slow

The dominant problem is not one expensive algorithm; it is many small correct
operations done independently:

- a contribution is selected;
- a resource is added;
- each binding is applied separately;
- each binding clones and rewrites AST;
- each rewrite rebuilds markers, hygiene, ports, and inventory;
- the scope inventory is refreshed/frozen after each change;
- target-site metadata is rediscovered repeatedly.

That is a sound general pipeline, but it behaves like a per-edge compiler pass
instead of a per-class compiler pass.

The lifecycle compiler also has a wide concept surface. The generated lifecycle
compiler currently includes many feature slices even when a specific class only
uses a subset:

```text
119 resources
184 contributions
113 matchers
113 assembly edges
CoreClassProduction: 103 apply steps
```

That means no-op or irrelevant feature layers still have selection and
assembly overhead unless they are filtered before the per-edge loop.

## Sub-1ms Target

The target should be interpreted carefully.

For an import-time runtime decorator, the desired budget is:

```text
< 1ms per decorated class after the lifecycle compiler module is already loaded
```

The current per-class budget is approximately:

```text
assembly:         575 ms
materialize AST:   83 ms
compile/exec AST:   1 ms
total:            659 ms
```

To hit sub-1ms:

- assembly must improve by roughly **500-600x**, or be skipped;
- materialization must improve by roughly **80x**, or be skipped;
- compile/exec is already close to the budget and should not be the focus.

The likely end-state is not "run the full general Astichi compiler in less than
1ms for every class." It is more likely:

1. YIDL files compile to a Python decorator module at package build time.
2. The decorator module owns a compact plan for a given concept.
3. Repeated decoration uses either:
   - a generated-AST/module cache keyed by harvested facts and tool versions; or
   - a specialized fast path that emits only the tiny class-specific deltas.
4. Full Astichi assembly remains available for cache misses, development,
   debugging, and golden generation.

## Second-Order Effects To Track

Once the first hotspot is fixed, another will dominate. These are the effects
that need explicit measurement so we do not optimize blindly.

### A. Binding Batch Size

Measure:

- number of binding specs per contribution;
- number of bindings per owner instance;
- number of owners touched per assembly;
- number of composable rebuilds avoided by batching.

Question:

```text
If all bindings for the same owner are batched, how many `bind_identifier`
and `bind` calls remain?
```

Expected impact:

- largest first-order win;
- may reduce inventory refreshes as a side effect;
- may reduce target-site cache invalidations.

### B. Owner Replacement Invalidation

Caching shell indexes and target names is straightforward until a binding
replaces an owner composable.

Measure:

- how often each owner is replaced;
- how many target-site validations hit a stable owner;
- how many cache entries are invalidated by bind operations.

Question:

```text
Are target-site cache entries long-lived enough to matter after binding
batching?
```

If batching means each owner is replaced once, target-site metadata can be
computed once before or after that replacement and reused for many target adds.

### C. Inventory Mutability

Immutable inventories are good API artifacts but expensive as construction
state.

Measure:

- inventory records added/removed per apply;
- total records copied by `_without_record_ids`;
- total records copied by `MutableInventory.freeze`;
- peak inventory size during lifecycle assembly.

Question:

```text
Can assembly use a mutable inventory internally and expose immutable snapshots
only for diagnostics/build boundaries?
```

Expected impact:

- lower second-order overhead after binding is batched;
- may simplify stable record-id handling for repeated occurrence records.

### D. Matcher/Edge No-op Cost

The lifecycle concept carries many feature layers. A class may not use many of
them.

Measure:

- per edge: records iterated, rules evaluated, contributions selected;
- how many edges select no contribution;
- how many selected contributions are empty suppression resources;
- how many apply edges are irrelevant for a class's field-kind set.

Question:

```text
Can the generated YIDL runtime pre-filter apply edges by available collections
or field kinds before entering Astichi assembly?
```

Expected impact:

- reduces constant factors;
- important after AST operations are no longer dominating.

### E. Materialization Policy

Materialization currently costs about 82ms per class.

Measure separately:

- `to_executable_ast`;
- `materialize`;
- `emit`;
- `emit_commented`;
- comment-preserving policy vs executable AST policy.

Question:

```text
Can runtime decoration request a minimal executable-AST finalization policy
that skips comment/provenance/source-only work?
```

Expected impact:

- required for sub-1ms if no cache is used;
- still useful for cache misses even with a cache.

### F. Generated AST Cache

If full assembly cannot hit sub-1ms, a cache must.

Measure:

- cache key construction cost;
- AST clone cost on cache hit;
- `compile(ast)` cost;
- module/class build cost;
- invalidation sensitivity to Python version, Astichi version, YIDL version,
  lifecycle YIDL source hash, and harvested facts.

Question:

```text
Can a cache hit return an executable AST or imported generated module in
under 1ms?
```

Compile/exec is already around 1ms per class, so a module cache that avoids
compile/exec entirely may be necessary for a strict sub-1ms target.

### G. Cold vs Warm Import

The first import pays normal Python import costs. Repeated decorator calls in
the same process should be measured separately.

Measure:

- cold process import;
- first decorator after module import;
- repeated decorator with same fact shape;
- repeated decorator with different class names but same structural shape.

Question:

```text
Which costs are one-time module initialization and which are per decorated
class?
```

This matters because LCM import currently decorates several similar classes in
one process.

### H. Structural Shape Scaling

The LCM profile covers 8 classes with similar shapes. We also need controlled
scaling data.

Measure:

- 1, 5, 10, 20, 50 fields;
- plain-only;
- managed-only;
- transient-only;
- managed with freeze/thaw;
- hooks/validators;
- mixed lifecycle field kinds.

Question:

```text
Is cost linear in contribution count after batching/incremental inventory, or
do hidden quadratic loops remain?
```

## Optimization Hypotheses

### H1: Batch Bindings Per Owner

Change YIDL assembly runtime and/or `AssemblyScope` so all bindings targeting
the same owner/build path are applied in one operation:

```text
current:
  bind identifier a -> rebuild
  bind identifier b -> rebuild
  bind external c   -> rebuild

target:
  bind identifiers {a, b} and externals {c} -> rebuild once
```

Expected win:

- collapses 616 identifier rebuilds and 421 external rebuilds toward the number
  of unique owner replacements;
- directly reduces `_rebuild_composable`, `clone_ast`, marker recognition,
  name analysis, inventory rebuild, and scope inventory refresh work.

Risk:

- some validators currently depend on seeing resolved identifiers during
  intermediate merge steps;
- batching must preserve diagnostics and rebind errors.

### H2: Cache Target-Site Metadata

Add an owner-composable metadata cache for:

- registered shell index;
- hole names;
- elif target names;
- param hole names.

Expected win:

- attacks the 560 repeated `_validate_registered_target_site` scans;
- may be very cheap to implement.

Risk:

- owner replacement by binding must invalidate cache entries;
- cache must distinguish build phase vs materialize phase if shell handling
  differs.

### H3: Mutable Assembly Inventory

Use a mutable inventory during assembly. Freeze only when returning public
metadata or producing diagnostics.

Expected win:

- reduces `_replace_occurrence_inventory` overhead;
- avoids repeated immutable inventory copy/freeze cycles.

Risk:

- diagnostics and candidate selection currently expect stable immutable records;
- record-id stability must be explicit.

### H4: Prune No-op Edges Before Astichi

Let generated YIDL runtime skip apply edges whose input collections are empty
or whose field-kind set proves the edge cannot contribute.

Expected win:

- reduces rule evaluation and candidate-search overhead;
- reduces noise from feature slices not used by a particular class.

Risk:

- must preserve matcher override semantics where an empty-looking feature can
  still contribute through inherited/default records.

### H5: Runtime Cache / Pre-generated Module Path

For strict sub-1ms runtime decoration, do not run full assembly on the hot path.

Expected win:

- turns runtime decoration into fact-key lookup plus class construction/import;
- likely required for the final target.

Risk:

- cache invalidation needs a precise version/source/fact key;
- generated modules need a packaging story;
- dynamic local functions/default factories still need to flow as runtime
  parameters, not serialized source.

## Immediate Next Measurements

Before changing behavior, add counters or trace hooks for:

- `scope.apply` by candidate type;
- `BasicComposable.bind_identifier`;
- `BasicComposable.bind`;
- `_rebuild_composable`;
- `recognize_markers`;
- `analyze_names`;
- `build_inventory`;
- `_validate_registered_target_site`;
- `_replace_occurrence_inventory`;
- `materialize_composable`.

Each counter should report:

- call count;
- total wall time;
- max wall time;
- owner/build path when useful;
- AST node count or inventory record count when useful.

The goal is to make optimization deltas visible without relying only on
cProfile.

## Current Priority Order

1. Implement binding batching or a prototype that proves the expected call-count
   reduction.
2. Add target-site metadata caching.
3. Replace repeated immutable inventory replacement with mutable assembly
   inventory.
4. Re-profile materialization once assembly is below 100ms per class.
5. Design the cache/pre-generated-module path needed for sub-1ms runtime
   decoration.

The first three are "make full assembly faster." The fifth is the likely
production answer for the strict sub-1ms target.
