# Native AST Probe

Status: tracked proof-of-concept module.

The native implementation does not have to be C++. The requirement is a native
compiler path that can parse, transform, and materialize Astichi templates
without using CPython AST objects as the working graph.

This probe is independent of the main Python lower-engine route-through. Its
job is to answer whether a native parser plus final CPython AST construction is
practical and fast enough to become the later native backend.

Use the `native_probe/` directory for the tracked probe module. Ignored
`scratch/native_probe/` files are local experiments and build artifacts only.

The tracked module currently uses Rust, PyO3, and `rustpython-parser`. It builds
with `native_probe/build.py`, exposes the probe API from
`native_probe/native_probe.py`, and keeps compiled extension artifacts out of
git.

## Hypothesis

Astichi can use this native pipeline:

```text
source text
  -> native parser
  -> native AST or normalized Astichi AST IR
  -> native template records, locators, and operation transforms
  -> materialized native AST artifact
  -> final CPython ast/_ast object construction
  -> compile(...)
  -> exec(...) when executable output is requested
```

The hot transforms should run without Python object churn and, where the native
language permits, without holding the GIL. CPython AST nodes are final artifacts,
not the assembly or transform graph.

GIL release is a future opportunity, not a success gate. The probe should record
where native work can run without the GIL, but success does not depend on
parallel Astichi execution until a higher-level caller actually consumes that
property.

## Candidate Parser Backends

Initial candidates:

- `ruff_python_parser`
- `rustpython-parser`

The probe should choose the parser that is easiest to embed and most compatible
with the Python grammar versions Astichi supports. A C++ wrapper, Rust/PyO3
extension, or hybrid native module are all acceptable implementation choices.
The backend choice should be evidence from the probe, not a design assumption.

## Probe Module Shape

The first module can live outside the production package until it earns its
place. A reasonable API is:

```text
parse_module(source: str, filename: str = "<astichi-probe>") -> ast.Module
compile_composable(source: str, filename: str = "<astichi-probe>") -> LowerComposable
copy_to_python_ast(composable: LowerComposable) -> ast.Module
to_source(composable: LowerComposable) -> str
bench_parse_convert(source: str, iterations: int) -> dict
```

`parse_module(...)` should return real CPython `ast`/`_ast` node instances so
the normal Python `compile(...)` API can validate and compile them.
`compile_composable(...)` is the more important Astichi-shaped probe: it should
parse with the native parser, keep the native tree as the working graph, and
return the common lower composable facade backed by the native engine.
`copy_to_python_ast(...)` and
`to_source(...)` are explicit artifact-copy operations for tests and parity.

Python does not execute AST nodes directly. The executable path is:

```text
lower_composable = compile_composable(source)
module = copy_to_python_ast(lower_composable)
code = compile(module, filename, "exec")
exec(code, namespace)
```

For `mode="exec"`, the root must be an `ast.Module`/`_ast.Module` with required
fields such as `body` and `type_ignores`.

`compile(...)` and `exec(...)` are test-harness actions that validate probe
output. They should not be exported as general-purpose execution helpers from
the probe module.

## CPython Boundary Policy

The default probe boundary is the public CPython AST API plus public
`compile(...)`. The probe should not depend on `PyArena`, `_PyAST_Compile`, or
other internal CPython compiler APIs.

Direct code-object generation through internal CPython APIs may be explored only
as a separate backend spike. It must not be required for lower-engine
correctness, structural snapshots, or golden parity.

## Minimal AST Surface

Start with the smallest executable subset:

- `Module`
- `Expr`
- `Assign`
- `Name`
- `Constant`
- `Call`
- `Attribute`
- `FunctionDef`
- `arguments`
- `arg`
- `Return`
- `ClassDef`
- `Import`
- `ImportFrom`

Then add Astichi-relevant surfaces:

- `If` / `elif` shape
- `With`
- function parameter defaults and annotations
- starred call arguments and keyword arguments
- `Try` and exception handlers
- `For` / `While` with `else`
- `Match` / `case`

The probe does not need Astichi semantics at first. It needs to prove parse,
convert, compile, and exec viability for syntax surfaces Astichi will later
transform.

## Location And Validation Policy

The final CPython AST must satisfy `compile(...)` validation. The probe should
measure both options:

- native code sets `lineno`, `col_offset`, `end_lineno`, and `end_col_offset`;
- native code sets minimal locations and Python calls `ast.fix_missing_locations`.

The probe should record which fields are mandatory for each supported Python
version and where `compile(...)` rejects malformed nodes.

The artifact emitter must also track recent and upcoming CPython constructor
strictness. Every emitted node should populate required fields, use valid
defaults for optional/list/context fields, and avoid unknown keyword arguments.
The probe should treat DeprecationWarning from AST constructors as a failure,
because those warnings become harder failures in newer Python versions.

The probe must produce a per-class constructor compatibility table for the
supported Astichi Python versions. At minimum, the table should record required
fields, defaultable fields, location requirements, notable structural validation
rules, and version-specific fields such as `type_params`.

Synthetic location policy must also be measured and documented. For nodes
inserted from one template into another, the probe should compare the current
Astichi behavior with candidate policies:

- keep the source-template authored location;
- use the target marker location;
- use a synthesized/composite location recorded in the structural snapshot.

## Measurements

Benchmark phases separately:

- `ast.parse(...)` baseline time;
- minimal Python template scan baseline time;
- combined `ast.parse(...) + minimal Python scan` baseline time;
- native parse time;
- native AST or IR construction time;
- CPython AST node construction time;
- lower composable facade construction time;
- artifact-copy time from lower composable to CPython AST;
- required/default field population time;
- location metadata population time;
- `ast.fix_missing_locations(...)` time, if used;
- optional source rendering time;
- `compile(...)` time;
- optional `exec(...)` time;
- GIL-held time, if measurable;
- total wall time.

Use:

- tiny hand-written modules;
- representative Astichi template modules;
- YIDL lifecycle-shaped templates;
- larger generated modules with repeated classes/functions.

The output should include node counts by AST class, source byte counts, parser
backend, Python version, native module build profile, and whether locations were
set natively or repaired by Python.

The probe is not useful without the baseline columns. Native timings must be
reported next to `ast.parse(...) + minimal Python scan` for the same input. A
native parser path should be considered strategically useful only when it is at
least 5x faster than that baseline on representative YIDL lifecycle-shaped
templates, or when it unlocks transform/materialization work that cannot be made
cheap in Python.

## Questions To Answer

- Can the chosen native parser handle the Python syntax Astichi needs now?
- How difficult is mapping parser nodes to CPython `ast`/`_ast` constructors?
- Can the parser output be wrapped in the common lower composable facade without
  first copying to CPython AST nodes?
- Can parse and native transforms run without the GIL?
- If GIL release is possible, what current caller can actually exploit it?
- Is final CPython AST construction cheap enough when done once per materialized
  artifact?
- How much time is spent populating required/default fields and location
  metadata?
- Is source rendering from the lower composable accurate enough for parity
  tests and debug output?
- Does direct CPython AST construction preserve enough location information for
  diagnostics and golden stability?
- Which synthetic location policy best preserves current traceback and golden
  behavior?
- Does the public `ast`/`_ast` plus `compile(...)` boundary suffice, or is there
  enough evidence to justify a separate internal-CPython compiler API spike?
- Is the native parser grammar close enough to CPython for Astichi's supported
  Python versions?
- Does this path beat `ast.parse(...)` plus Python transforms on representative
  templates?
- Does it beat the baseline by enough to justify tracking a second grammar?

## Success Criteria

The probe is useful if it can:

- return a CPython AST module that `compile(...)` accepts;
- return a lower composable facade whose native-engine working graph is not
  CPython AST;
- copy that wrapper to CPython AST for explicit artifact/parity testing;
- execute the compiled code through `exec(...)`;
- support the minimal AST surface plus at least one Astichi-relevant surface;
- include a baseline comparison against `ast.parse(...) + minimal Python scan`;
- run all current `tests/data/gold_src/` fixtures through the chosen parser plus
  the engine-selection fallback policy;
- produce the per-class constructor compatibility table;
- document the synthetic location policy and current-behavior comparison;
- report parse, convert, lower composable wrapping, artifact copy,
  required/default field population, location population, compile, and exec
  timings separately;
- identify the dominant cost after native parsing and conversion.

The probe is strong enough to influence the native backend plan if it shows that
native parse/transform plus final CPython AST construction is materially faster
than Python `ast` parsing and transformation for representative Astichi/YIDL
templates.

## Non-Goals

- no full Astichi lower engine;
- no full surface registry;
- no complete hygiene implementation;
- no commitment to Rust, C++, or a hybrid backend;
- no dependency on internal CPython compiler APIs;
- no production packaging decision.

The probe answers whether the native AST path is viable. The main lower-engine
design still owns correctness, snapshots, and golden parity.

## Slice 14a Result

The 2026-05-25 decision profile keeps this probe as valid evidence, but does
not use it to justify starting the full native lower-engine implementation.
The probe parsed and converted all current `tests/data/gold_src/*.py` fixtures
without fallback, and fixture-shaped native parsing beat
`ast.parse(...) + minimal Python scan`. The win was not the 5x threshold, and
artifact-copy cost remained significant.

See `NativeDecisionProfile.md` for the current gate result.
