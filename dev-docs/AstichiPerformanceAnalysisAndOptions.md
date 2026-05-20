# Astichi Performance Analysis and Options

Status: analysis / proposal.

This document characterizes the observed performance of the astichi build pipeline
under a representative high-workload YIDL assembly, locates where time is spent,
sets a realistic target by benchmarking the underlying Python primitives, and
enumerates architectural options for closing the gap. The focus is the cost of
**building code** — the per-assembly cost of going from a set of authored
composables and assembly directives to one materialized source string. Test-suite
ergonomics (e.g. tests invoking the same assembly more than once) are explicitly
out of scope; the goal here is to make a single assembly fast.

## TL;DR

For the slowest YIDL golden case
([`yidl/tests/data/gold_src/yidl_update_a_dataclasses_split.py`](../../yidl/tests/data/gold_src/yidl_update_a_dataclasses_split.py)),
which produces one `Widget` dataclass with seven fields:

- The slow work is **not** the YIDL generator that emits `decorator.py`. The
  generator (parse four `.yidl` files + emit a ~636-line decorator source via
  `emit_concept_runtime_source`) takes **~270 ms** end-to-end. That part is
  fine.
- The slow work is the **decorator runtime**: each call to
  `build_DataclassModule(container).emit_commented()` — the step that produces
  one Widget dataclass module from declared field metadata — takes **~23–24 s
  of wall time** in isolation (and is the apples-to-apples analog of Python's
  own `@dataclass(...)`).
- **~91% of that decorator-runtime wall time is inside one astichi function**:
  `BuilderHandle.build` → `materialize.api.build_merge`.
- **346 of 358 `build_merge` calls (~97 %) are throwaway**: yidl's
  `AssemblyScope._refresh_inventory()` triggers a full graph rebuild after every
  applied contribution, only to read back `.inventory`. Those 346 calls
  account for **~91 % of cumulative `build_merge` time**. This is the
  dominant cost driver and an unambiguous **O(N²)** loop in the number of
  contributions.
- Within each `build_merge`: `copy.deepcopy` accounts for ~42 % of self-time,
  raw AST traversal (`ast.walk` / `iter_child_nodes` / `visit` / `generic_visit`)
  accounts for another ~22 %, with the rest split across hygiene, port
  extraction, provenance propagation, and insert-shell construction.
- **Reference baseline**: Python's own `@dataclass(frozen=True)` decorates an
  equivalent Widget class in **~0.23 ms**. Even `ast.parse + ast.unparse` on
  the full ~636-line decorator source takes only **~21 ms**. The current ~23 s
  per decorator-runtime invocation is **~1 100× slower than re-parsing
  astichi's own output** and **~100 000× slower than the equivalent
  @dataclass call** — for the same observable result (one Widget dataclass
  ready to use).
- Several composable architectural changes (inventory updates without
  re-merging; declarative assembly plan with a single batched merge;
  per-pass instead of per-contribution AST walks) are plausibly sufficient to
  reach **~20–100 ms per decorator-runtime invocation**, i.e. **~250–1100×
  faster than today**.

## 1. Measurement methodology

All measurements taken from the parent checkout at HEAD on 2026-05-20 against
the YIDL golden test
[`yidl/tests/data/gold_src/yidl_update_a_dataclasses_split.py`](../../yidl/tests/data/gold_src/yidl_update_a_dataclasses_split.py)
(43rd-slowest test of 43; the slowest yidl golden by a factor of ~2×).

- Profiled run: `cProfile` wrapping `runpy.run_path(...)` of the gold-src script.
  Total cProfile-instrumented time: **123.5 s**; uninstrumented wall time:
  **~35 s** (cProfile overhead ~3.5×). Ratios in this document refer to the
  cProfile breakdown but absolute targets are quoted in wall time.
- Python baseline microbenchmarks: `time.perf_counter()` over 2 000–100 000
  iterations on Python 3.12 in the same `uv` environment, after warm-up. The
  Widget shape used for the @dataclass benchmark mirrors the YIDL test's
  Widget exactly (7 fields: instance, default, default_factory, InitVar,
  init=False/repr=False, ClassVar, and `__post_init__`).
- The test invokes the same decorator runtime more than once for unrelated
  reasons; per-invocation costs below are reported in isolation. The
  meaningful end-user number is "one decorator-runtime invocation produces
  one Widget class".

## 2. Phase decomposition

A standalone benchmark that mirrors the test workflow exactly, run outside
cProfile, gives this phase breakdown (one full assembly producing one Widget
dataclass module):

| Phase | Wall time | One-time / per-use | Notes |
| --- | ---: | --- | --- |
| 1. YIDL parse (4 `.yidl` files via `compile_yidl_files`) | 104 ms | one-time | Lexes and compiles the concept |
| 2. YIDL generator (`emit_concept_runtime_source`) | 158 ms | one-time | Emits the `decorator.py` source (~636 lines) |
| 3. `exec(decorator_source, namespace)` | 12 ms | per-use | Standard Python compile/exec |
| 4a. Container build (declare 7 fields via builder) | 0.06 ms | per-use | Pure-Python field metadata |
| **4b. Decorator runtime: `build_DataclassModule(container).emit_commented()`** | **~23 400 ms** | **per-use** | **The slow part. Apples-to-apples with `@dataclass(Widget)`.** |
| 5. `black.format_str(decorator_source)` | 839 ms | one-time | Whole-file black format of the 636-line decorator |
| 5'. `black.format_str(generated_output)` | 17 ms | one-time | Black format of the 62-line generated module |

The total wall time of phases 1–5 in one assembly cycle is ~25 s. Phases 1+2
(YIDL generator) sum to **~270 ms**, which is roughly proportional to what
parsing and re-emitting the generated source independently costs (§3). The
generator is fine. The decorator runtime — astichi's per-Widget assembly —
is the entire problem.

The decorator-runtime cost is stable across invocations: repeated runs on
the same warm namespace measured 23.4 s / 22.8 s / 22.9 s / 22.6 s for
the first four calls.

> **Note on the two per-invocation numbers in this document.**
> The standalone benchmark above reports **~23 s per decorator-runtime
> invocation**. The cProfile-instrumented test run reports 4 top-level
> `run_assembly` calls in 114.7 s cumulative profile time = an *average* of
> **~8 s wall per call** after dividing out the ~3.5× cProfile overhead.
> The two numbers disagree by ~3× and we have not fully reconciled them: the
> simplest theories are (a) the cProfile cumulative is non-uniform across the
> 4 calls (the diagnostic-raising calls finish much earlier than the full
> runtime calls), pulling the average down, or (b) the standalone benchmark
> incurs per-call overhead the in-test back-to-back calls do not. Either way,
> **the in-test per-invocation cost is in the range 8–23 s of wall time**,
> and the gap to the ~0.23 ms `@dataclass` baseline is large enough that the
> qualitative conclusions in §4 and §7 are robust to this measurement noise.
> Ratios below use **~23 s** as the conservative single-invocation number;
> ratios anchored on the *test-overall* wall time use the measured 34 s.

## 3. Where time goes inside the decorator runtime

All numbers below are from cProfile-instrumented runs of the full test
script. The cProfile data covers all four `build_DataclassModule(...)`
invocations the test issues; ratios between rows are stable across calls.

### 3.1 Top-level decomposition

Out of 123.5 s under cProfile:

| Component | cProfile time | % | Wall (estimated) |
| --- | ---: | ---: | ---: |
| Inside `materialize/api.py:build_merge` (358 calls) | 113.9 s | 91 % | ~32 s |
| Outside `build_merge` (decorator exec, `black`, validate, etc.) | 9.6 s | 8 % | ~3 s |
| **Total** | **123.5 s** | **100 %** | **~35 s** |

`build_merge` is `astichi.materialize.api.build_merge` (`api.py:958`), reached
through `BuilderHandle.build` (`handles.py:1237`).

### 3.2 Who calls `build_merge`

| Caller | Calls | Cumulative time | Notes |
| --- | ---: | ---: | --- |
| `AssemblyScope._refresh_inventory` ([`astichi/src/astichi/assembler/scope.py:337`](../src/astichi/assembler/scope.py)) | **346** | 103.6 s | Thrown away after reading `.inventory`. **The bottleneck.** |
| `AssemblyScope.build` (final per-assembly) | 12 | 10.3 s | Real builds. Four top-level assemblies × ~3 nested productions. |
| **Total** | **358** | **113.9 s** | |

The scope refresh is the single highest-leverage hotspot. The relevant code is:

```337:342:astichi/src/astichi/assembler/scope.py
    def _refresh_inventory(self) -> None:
        instances = self.builder.graph.instances
        if not instances:
            self._inventory = empty_inventory()
            return
        self._inventory = self.builder.build(unroll=False).inventory
```

It runs once per applied contribution. With ~90 contributions per assembly and
4 assemblies in the slowest test, that's 360 refresh calls. Each refresh runs
the full astichi merge pipeline against the *current* graph size, so total
work scales as **Σ k from 1 to N**, i.e. quadratic in contribution count. The
fraction of essential work in `build_merge` is ~9 %; the other ~91 % is
repeated.

### 3.3 What `build_merge` itself spends time on

Self-time / cumulative time inside `build_merge` (one merge averages ~318 ms
under cProfile, ~90 ms wall):

| Operation | self time | cum time | calls | Comment |
| --- | ---: | ---: | ---: | --- |
| `copy.deepcopy` family (`_deepcopy_dict`/`_list`/`_reconstruct`) | ~34 s | 47.6 s | 71.8 M | Per-contribution body copy in `_make_block_insert_shell` + bind() / bind_identifier() rebinding |
| `_make_block_insert_shell` ([`api.py:1508`](../src/astichi/materialize/api.py)) | 0.33 s | **40.8 s** | 1 396 | Wraps every contribution body with a fresh `astichi_insert`-decorated function shell, deep-copying every statement |
| `_wrap_in_root_scope` ([`api.py:1609`](../src/astichi/materialize/api.py)) | 0.002 s | 26.1 s | 358 | Per-merge root wrapping |
| AST traversal: `ast.walk` / `iter_child_nodes` / `iter_fields` / `visit` / `generic_visit` | ~28 s | ~75 s | >100 M | Marker scan, classification, hygiene, port extraction |
| `propagate_astichi_source_file` ([`ast_provenance.py:89`](../src/astichi/ast_provenance.py)) | 0.9 s | 8.9 s | 217 k | Provenance metadata propagated by mutation |
| `_locally_satisfied_hole_names` ([`api.py:3415`](../src/astichi/materialize/api.py)) | 1.8 s | 10.3 s | 4 003 | Hole-resolution lookup |
| `inventory.visit` (`model/inventory.py:455`) | 2.9 s | 5.5 s | 1.94 M | Inventory record walking |

The **leaf-level hottest operation** is
`[copy.deepcopy(stmt) for stmt in body]` inside `_make_block_insert_shell`
([`api.py:1522–1524`](../src/astichi/materialize/api.py)). Every rebuild
re-deepcopies every contribution body to wrap it in a new shell, even though
the body itself never changed.

The second-tier hot work is AST traversal that is run **once per contribution
per rebuild**: classify names, locate markers, resolve ports, walk for
hygiene-relevant identifiers. With 358 merges and ~90 contributions each, the
same nodes are revisited tens of millions of times.

## 4. Reference target: Python's own primitives

To set a realistic ceiling for what "one decorator runtime invocation" should
cost, we benchmarked the underlying Python machinery (Python 3.12, same `uv`
environment as the test run). All numbers below are wall-time, no profiler.

| Operation | Median latency | Apples-to-apples comparison |
| --- | ---: | --- |
| `@dataclass(frozen=True)` decoration of the equivalent Widget class | **0.23 ms** | "produce one Widget class ready to instantiate" — direct analog of the YIDL decorator runtime |
| `exec` of a hand-written Widget dataclass source string | **0.26 ms** | "load one Widget class from source" — also analogous |
| `ast.parse` of the emitted YIDL `decorator.py` (636 lines) | **11.6 ms** | floor for *just reading* astichi's own output |
| `ast.parse` + `ast.unparse` of the same `decorator.py` | **20.7 ms** | floor for *re-emitting* astichi's own output |
| `ast.parse` of the emitted `generated_output.py` (62 lines) | **0.29 ms** | parse the final dataclass module |
| `ast.parse` + `ast.unparse` of `generated_output.py` | **0.57 ms** | parse + emit the final dataclass module |

The 20.7 ms figure is the most informative ceiling: that is how long it takes
**just to parse and re-emit the text that astichi already produced**, with no
merging, hygiene, marker logic, or boundary wiring. The current decorator
runtime spends **~23 000 ms** producing it. That is a **~1 100× gap**
between observed cost and the floor of source-text manipulation.

Stated as ratios against today's ~23 s per decorator-runtime invocation:

| Baseline | Ratio (today vs baseline) |
| --- | ---: |
| Python `@dataclass` decoration | **~100 000× slower** |
| `exec` of hand-written source | **~88 000× slower** |
| `ast.parse(decorator.py)` | **~1 970× slower** |
| `ast.parse + ast.unparse(decorator.py)` | **~1 100× slower** |

The first two ratios are aspirational: astichi has to do more work than
simply executing one already-known class definition (it materializes a
configurable Widget from declared field metadata, including markers,
hygiene, provenance, and source emission). The last two ratios are
squarely within the same complexity class as what astichi does (produce
one AST and emit it as text). They represent a credible target: **the
decorator runtime should plausibly land near 20–100 ms**.

> **YIDL generator stays out of this comparison.** Phases 1 + 2 (parsing
> `.yidl` files and emitting `decorator.py`) total ~270 ms and have no
> direct Python analog — they are effectively "writing the @dataclass
> implementation", not "running it". 270 ms is acceptable for a one-time
> code-emission step and is not the focus of this document.

## 5. Why we are this slow

The findings consolidate into three structural causes, in order of impact:

### 4.1 Quadratic per-contribution rebuild

`AssemblyScope` re-runs the full merge pipeline after every `scope.apply()` to
read back `.inventory`. The current code is correct (the inventory must
reflect prior contributions before the next one is selected), but the
implementation conflates "give me the current inventory" with "do the whole
merge again". This accounts for ~94 % of `build_merge` cost on assembly-heavy
workloads.

### 4.2 Per-contribution AST passes

Each `build_merge` walks every contribution's AST once per pass (marker
classification, name analysis, hygiene unification, port extraction, source-
file provenance). When the same merge runs N times against progressively
larger graphs, the **same nodes are visited Θ(N²) times** for what is
logically one classification job per node.

### 4.3 Eager deepcopy at the merge boundary

`_make_block_insert_shell` deep-copies every contribution's body on every
merge, even when the body is immutable between merges. Bind rebinding
(`Composable.bind` / `bind_identifier`) also deep-copies the entire tree
before applying a tiny set of substitutions. Both copy the full AST when, in
practice, structural sharing with copy-on-write or lazy substitution would
suffice until the final emit step.

## 6. Architectural options

The options below are roughly orthogonal: each can be adopted independently,
but most compose. For each we give an **estimated wall-time floor for one
YIDL assembly on the Widget workload** based on the cProfile breakdown.

### Option A — Incremental inventory in `AssemblyScope`

Replace `_refresh_inventory`'s full `build(unroll=False).inventory` with an
update path that only does the work caused by the most recent contribution
(union the contributor's own inventory records into the scope inventory,
flip port-satisfaction flags for `_apply_external_value` /
`_apply_identifier_name`, etc.).

- Files: [`astichi/src/astichi/assembler/scope.py`](../src/astichi/assembler/scope.py),
  plus a new public surface on `astichi.model.Inventory` to "merge in" one
  instance's inventory records and "satisfy" one port by id.
- Risk: medium. The merging logic exists implicitly inside `build_merge`; we
  need to extract or duplicate the relevant subset.
- Floor: **~2 s wall** per decorator-runtime invocation. Today's
  ~23 s includes ~22 s of throwaway refreshes (94 %); eliminating those
  leaves only the work of the final merge plus its own materialize/emit
  cost.

### Option B — Declarative assembly plan + single batched stitch

Restructure yidl's `assembly_runtime` so the `_run_edge` loop produces an
`AssemblyPlan` (a list of directives: `(composable, instance_name, target
selector, bindings, order)`) without touching the astichi builder graph at
all. Astichi grows a `materialize_plan(plan)` entry point that resolves
symbolic target selectors against the merged inventory in a single pass.

- Files (this side of the boundary): [`astichi/src/astichi/materialize/api.py`](../src/astichi/materialize/api.py)
  (new `materialize_plan` entry), [`astichi/src/astichi/assembler/scope.py`](../src/astichi/assembler/scope.py)
  (becomes mostly obsolete).
- yidl side: `assembly_runtime` is rewritten to be plan-emitting rather than
  graph-mutating. Out of scope for this document.
- Risk: medium-high. Per-contribution diagnostic locality has to be preserved
  by carrying source-location records on plan entries; `require_one` becomes
  a plan-validation step.
- Floor: **~2 s wall** per decorator-runtime invocation (same as A; the
  bottleneck is the same final-merge cost). The architectural payoff is
  cleaner code, not a deeper speedup ceiling on its own.

A and B are *competing approaches to the same problem*; they don't compose.
B is a cleaner long-term shape; A is a smaller surgical fix.

### Option C — Batched merge that does each pass once over all contributions

Restructure `build_merge` so the work that is currently done per contribution
per rebuild — marker scan, name classification, hygiene unification, port
extraction, provenance propagation — runs **once over the merged tree** with
all contributions known upfront, instead of N times.

Concretely, `_make_block_insert_shell` and the surrounding marker analysis
should treat the contribution list as a single workitem: one walk over each
contribution body to extract markers and ports, one global hygiene-rename
pass on the union, one provenance walk. This requires moving from a
"contribution at a time" pipeline to a "union at a time" pipeline.

- Files: [`astichi/src/astichi/materialize/api.py`](../src/astichi/materialize/api.py)
  (`build_merge` and the helpers it dispatches to: hygiene assignment, hole
  resolution, insert-shell construction).
- Risk: high. This is the most invasive change; needs a careful audit of
  every per-merge AST mutator (markers, hygiene, provenance, indexed-instance
  bookkeeping) to ensure the union-time variant is order-independent and
  preserves existing semantics.
- Floor: **~400–700 ms wall** per decorator-runtime invocation (when stacked
  on A or B). The dominant cost stops being N × per-contribution walks and
  becomes one walk of size proportional to the final emitted AST.

C composes with either A or B (it reduces the cost of each *remaining*
merge).

### Option D — Copy-on-write / lazy substitution for `bind` and shell construction

Today, `BasicComposable.bind` and `bind_identifier` deep-copy the entire
composable tree before applying a small substitution set. Similarly,
`_make_block_insert_shell` deep-copies every contribution body even though
the body hasn't changed between rebuilds.

Replace this with:
- A `BoundComposable` wrapper that records the substitution map without
  copying the tree. The substitution is applied once during the final
  emit pass.
- Memoization of `_make_block_insert_shell(body, target_name, order, ref_path)`
  keyed by `id(body)`. Each contribution body is a stable object; the
  wrapping is deterministic.

- Files: [`astichi/src/astichi/model/basic.py`](../src/astichi/model/basic.py)
  (`bind`, `bind_identifier`),
  [`astichi/src/astichi/materialize/api.py`](../src/astichi/materialize/api.py)
  (`_make_block_insert_shell`, `_wrap_in_root_scope`, the in-place
  mutator passes).
- Risk: medium. The blast radius is the set of in-place AST mutators
  (`propagate_astichi_source_file`, hygiene renamers, source-location
  patchers). Each one needs to either become functional or be deferred to
  the final emit step.
- Floor when stacked on A or B: **~1 s wall** per decorator-runtime invocation.
  When stacked on A/B + C: **~80–150 ms wall**.

D composes with all of A, B, C. The shell memoization sub-fix alone (no
broader COW work) is a ~30-line patch with most of D's marginal value when
the quadratic refresh is still present, and ~0 marginal value once A/B is
in place.

### Option E — Defer provenance / hygiene to emit

Several passes that are currently run inside `build_merge` are only observed
externally at emit time:

- `propagate_astichi_source_file` is consumed by `emit_commented()` and
  diagnostics, not by intermediate merges.
- Hygiene renames are consumed by the final emitted text; intermediate
  composables don't need to "see" the renamed identifiers.

Moving these into a single pass during `materialize.emit` (or
`emit_commented`), driven by the final merged tree, avoids paying for them
on every intermediate rebuild even when A or B has already reduced the
number of rebuilds.

- Files: [`astichi/src/astichi/ast_provenance.py`](../src/astichi/ast_provenance.py),
  [`astichi/src/astichi/hygiene/api.py`](../src/astichi/hygiene/api.py),
  emit-side glue.
- Risk: medium. Any caller that introspects `arg_bindings`, `keep_names`, or
  hygiene-renamed identifiers on an intermediate composable will need to
  switch to the post-merge form.
- Floor: small standalone improvement (~10–20 % of build_merge). Useful
  primarily as a multiplier on top of C.

## 7. Projected wall time per decorator-runtime invocation by combination

All rows refer to **one decorator-runtime invocation** (the apples-to-apples
analog of one `@dataclass(Widget)` call). Today's full-test wall time is
roughly two such invocations plus ~270 ms of generator work plus ~0.85 s of
black-format work plus small overhead.

| Option set | One decorator-runtime invocation (est.) | Ratio vs today |
| --- | ---: | ---: |
| Today | **~23 s** | 1× |
| A *or* B (incremental inventory / declarative plan) | ~2 s | ~12× |
| A or B + D (COW + memoization) | ~1 s | ~25× |
| A or B + C (batched merge) | ~400–700 ms | ~35–60× |
| A/B + C + D + E (full stack) | **~80–150 ms** | **~150–300×** |
| `ast.parse + ast.unparse` of emitted source (floor) | ~21 ms | ~1 100× |
| Python `@dataclass` (theoretical floor for "build one class") | ~0.23 ms | ~100 000× |

The realistic engineering target is the **~80–150 ms** row: within ~5–7× of
re-parsing the already-emitted source. Pushing below that requires bypassing
the textual emit step entirely (e.g. emitting Python class objects directly
rather than source), which is a separate architectural question and out of
scope here.

The ~91 % share of throwaway work in `build_merge` (from §3.2) is the upper
bound on what option A or B alone can recover — that is where the **~12×**
single-step speedup comes from. Options C, D, E attack the *residual* per-
merge cost that survives once the loop is eliminated.

## 8. Recommendations

In priority order, with each step justified by the projection above:

1. **Build the incremental-inventory surface** that Option B would also use:
   a small `Inventory.merge_instance(...)` / `Inventory.satisfy_port(...)`
   public API on the astichi side, plus replacement of
   `AssemblyScope._refresh_inventory`'s body with a function call that
   reflects only the latest applied candidate. This is the highest-leverage
   single change and is a prerequisite for either A or B.
2. **Decide between A and B as the long-term shape.** B (declarative plan +
   batched stitch) is the cleaner contract and aligns with the proposal in
   [`AtichiBuildResolverProposal.md`](AtichiBuildResolverProposal.md); A is
   an in-place surgical fix that ships sooner. Both reach the same floor.
3. **Stack Option C (batched merge)** once the inventory bottleneck is gone.
   This is where the next order of magnitude lives and is the most invasive
   change; the work makes more sense after the call graph has been
   simplified by 1–2.
4. **Stack Option D (COW + shell memoization)** as a follow-up — most of D's
   value is captured by C, but the memoization piece is cheap enough to keep
   as a standalone PR if any per-rebuild work survives.
5. **Treat Option E as a polishing pass** for the final ~20 % of the
   build_merge budget once the major rewrites have landed.

## 9. Open questions

- **Inventory record identity stability**: incremental inventory merging
  depends on stable, comparable record ids. Today's `build_merge` recomputes
  ids from scratch each call. We need to verify they are functions of stable
  inputs (composable identity + instance name + edge order) before we can
  trust incremental merge results to match full-rebuild results.
- **Cross-instance hygiene constraints**: the hygiene/keep-name analysis runs
  globally across the whole merged tree today. A batched merge has to
  preserve the global-view invariant; piecewise hygiene unification needs
  proof that it produces the same fixed point as the full pass.
- **Diagnostic locality**: `_apply_composable` today raises with a specific
  contribution context. A plan-validated batched merge needs source-location
  threading on plan entries so user-facing error messages remain actionable.
- **Final-merge cost lower bound**: even with all options, the final merge
  has to do at least one walk over the union tree. We have not measured a
  "from-scratch single-build" cost on the same workload; that would tell us
  whether the ~50–100 ms target is realistic or optimistic. Suggested next
  measurement: time `astichi.build()` end-to-end on a hand-built equivalent
  graph (all 90 contributions added without intermediate `_refresh_inventory`),
  then compare against the projections in section 6.

## 10. Benchmark reproduction

The benchmark scripts used in section 3 are kept under
[`docs/validation/perf/`](../docs/validation/perf/) (TODO: promote from a
local scratch directory when this proposal is acted on). Profile capture was:

```bash
PYTHONPATH=yidl/tests/data/gold_src \
  uv run --with pytest python -c "
import cProfile, sys, runpy
sys.argv = ['yidl_update_a_dataclasses_split.py', 'scratch/yidl_perf/out']
prof = cProfile.Profile(); prof.enable()
try: runpy.run_path('yidl/tests/data/gold_src/yidl_update_a_dataclasses_split.py', run_name='__main__')
except SystemExit: pass
prof.disable(); prof.dump_stats('scratch/yidl_perf/profile.prof')
"
```

Top-N views:

```bash
python -c "import pstats; pstats.Stats('scratch/yidl_perf/profile.prof').strip_dirs().sort_stats('cumulative').print_stats(30)"
python -c "import pstats; pstats.Stats('scratch/yidl_perf/profile.prof').strip_dirs().sort_stats('tottime').print_stats(30)"
```
