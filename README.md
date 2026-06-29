# astichi

[![PyPI version](https://img.shields.io/pypi/v/astichi.svg)](https://pypi.org/project/astichi/)
[![Python versions](https://img.shields.io/pypi/pyversions/astichi.svg)](https://pypi.org/project/astichi/)
[![License](https://img.shields.io/pypi/l/astichi.svg)](https://github.com/owebeeone/astichi/blob/main/LICENSE)

**A declarative, runtime code generator for Python.**

Astichi stitches small, marker-bearing Python snippets into specialized code
**at runtime** — for example, inside a class decorator that assembles a tailored
implementation each time it is applied — and emits plain, inspectable Python that
then runs with no per-call dispatch overhead. An optional native Rust engine
keeps that runtime generation fast enough to sit on the decoration / import path.

The point is to make AST stitching **declarative**: you say *what* fills which
hole and *what* satisfies which injection point — even partially — and astichi
**connects the dots for you**. It matches snippets to compatible holes, values to
their binding slots, and identifiers to their demands (with a real
compatibility check, not string-matching), wires them across nested layers, and
keeps every scope hygienic. You describe the graph; you don't hand-walk and
mutate an AST.

It is a focused, hygienic **AST stitcher** — it composes generator-authored
fragments; it is not a generic codemod or refactoring framework for existing
source.

```bash
pip install astichi
```

Release wheels for Linux, macOS, and Windows (CPython 3.12–3.15) bundle an
optional native Rust acceleration engine; installs without a matching wheel fall
back to pure Python. See [the native fast path](#native-rust-fast-path).

## Quick start

You author Python with **markers** in it, compile each snippet into a
`Composable`, wire them together with a **builder**, then **materialize** and
**emit** real Python.

```python
import astichi

root = astichi.compile("""
items = []
astichi_hole(body)            # a named insertion site
result = tuple(items)
""")

step = astichi.compile("""
astichi_pass(items, outer_bind=True).append("x")   # explicitly reuse outer `items`
""")

builder = astichi.build()
builder.add.Root(root)
builder.add.Step(step)
builder.Root.body.add.Step(order=0)   # stitch `step` into the `body` hole

print(builder.build().materialize().emit(provenance=False))
```

Emitted Python:

```python
items = []
items.append("x")
result = tuple(items)
```

Without `astichi_pass(items, outer_bind=True)`, the inner snippet would *not*
silently reuse `items` just because the spelling matches. Astichi defaults to
isolated scopes and only crosses them when the source says so — that is the
hygiene guarantee that makes large stitched programs predictable.

For the full compile → bind → build → describe → materialize → emit walkthrough,
see the **[Using the API guide](https://github.com/owebeeone/astichi/blob/main/docs/guide/using-the-api.md)**.

## What you get

- **Connect-the-dots wiring.** Hand astichi a snippet, a value, or an identifier
  plus a *partial* description of where it goes, and it finds the compatible hole
  / binding slot / demand and attaches it — checking structural compatibility, not
  just names. You under-specify; it resolves the match (and refuses ambiguous
  ones with a diagnostic). This is the declarative core; see
  [the assembler](#declarative-wiring-the-assembler-connects-the-dots).
- **Multi-layer composition.** Composables compose into composables: build one,
  reuse it as a piece of the next, nest child scopes, and wire identifiers
  *across* layers — with hygiene preserved at every boundary.
- **Valid ASTs, not string fragments.** Compose typed AST nodes with
  deterministic insertion order instead of concatenating text.
- **Hygiene by default.** Each inserted snippet lives in its own scope. Names
  cross boundaries only through explicit `keep` / `pass` / `import` / `export`,
  so stitched fragments never collide by accident.
- **Generation-time specialization.** Bake values into the source and unroll
  `astichi_for(...)` loops into straight-line Python *as you generate* — so the
  emitted function carries no dispatch layer to pay for on every call.
- **Managed imports.** Snippets declare the imports they need with
  `astichi_pyimport(...)`; astichi collects, dedupes, collision-checks, and
  inserts them at materialize time.
- **Inspectable output.** Emitted source can be diffed, tested, and round-tripped,
  optionally with a provenance tail for AST/source-location restoration.
- **Descriptor-driven composition.** `describe()` exposes holes, binds, ports,
  and target addresses so tools can wire fragments from data instead of
  hand-written attribute chains.

## The marker model

> **These are not functions you import or call.** `astichi_hole`,
> `astichi_keep`, `astichi_pass`, and the rest are **markers** — sentinel names
> recognized in the Python *source text* you hand to `astichi.compile(...)`.
> There is **no** `from astichi import astichi_hole`; you write the marker inside
> the snippet string and astichi recognizes it by name and **AST position** (not
> by string matching alone). The only names you actually import from `astichi`
> are `compile`, `build`, `Composable`, and a few helpers.

The core markers are:

- `astichi_hole(name)` -> insertion site
- `astichi_keep(name)` -> hygiene-preserved name in expression / statement source
- `name__astichi_keep__` -> hygiene-preserved name in identifier position
- `name__astichi_arg__` -> identifier demand
- `name__astichi_param_hole__` -> function-parameter insertion target
- `astichi_funcargs(...)` -> call-argument payload
- `astichi_for(...)` -> build-time loop unrolling
- `astichi_bind_external(name)` -> external/literal value slot
- `astichi_ref(path)` -> compile-time reducible identifier / attribute path
- `astichi_pyimport(module=..., names=(...))` -> managed Python import
- `astichi_comment("...")` -> final-output source comment
- `astichi_pass(name, outer_bind=True)` -> explicit same-name boundary read
- `astichi_import(name)` -> explicit whole-scope boundary import
- `astichi_export(name)` -> explicit outward supply
- `astichi_insert(...)` -> internal emitted metadata, not general authored API

Comment marker note:

- `astichi_comment("...")` is statement-only. Ordinary `materialize()` strips
  it for executable output; `emit_commented()` renders it as real `#` comments.
- Multi-line payloads keep the marker statement's indentation, and only exact
  `{__file__}` / `{__line__}` substrings are expanded.

Value-form target note:

- `astichi_ref(...)` and `astichi_pass(...)` are ordinary value-form surfaces in
  expressions.
- If the marker result itself must occupy an `Assign` / `AugAssign` / `Delete`
  target position, append `._` or `.astichi_v`:
  `astichi_ref("self.f0")._ = 1`,
  `astichi_pass(counter).astichi_v = 1`.
- If you immediately continue to a real attribute, plain Python target syntax
  already works:
  `astichi_pass(obj).field = 1`.

The one rule that matters most is scope:

- `astichi_insert` is the basic Astichi boundary.
- Each inserted composable lives in its own Astichi scope.
- There is no implicit capture across that boundary.
- If a name crosses the boundary, make it explicit with `keep`, `pass`,
  `import`, or `export`.
- Function parameters are the pinned exception: parameter names and uses in the
  function scope stay attached to that parameter binding.

The full marker reference, edge cases, and value-form target rules live in the
**[marker docs](https://github.com/owebeeone/astichi/blob/main/docs/reference/marker-overview.md)**
and
**[scoping & hygiene reference](https://github.com/owebeeone/astichi/blob/main/docs/reference/scoping-hygiene.md)**.

## Declarative wiring: the assembler connects the dots

This is the part that makes astichi feel low-fuss. The hardest, most
error-prone part of stitching code by hand is the bookkeeping: *which* snippet
is allowed in *which* hole, *which* value feeds *which* injection point, *which*
identifier answers *which* demand — and keeping all of that straight as the
graph grows across layers. `astichi.assembler.AssemblyScope` does that matching
for you.

The plain fluent builder makes you name the exact target up front
(`builder.Root.body.add.Step()`). The assembler inverts it: you hand it a
**resource** plus a **partial description** of where it belongs, and it
**finds the site that resource can legally satisfy** — a block hole, an
identifier demand, an external-value slot — using a structural **compatibility
check** against the target's descriptor, not string-matching. Under-specify and
it resolves the match; if more than one site fits, it refuses with a diagnostic
rather than guessing. That is the "connect the dots" behavior: you declare
intent, astichi does the wiring.

It is built from three small, composable pieces:

1. **Pluggable resources** — *what* to attach: `as_composable(...)` (a fragment),
   `as_external_value(...)` (a compile-time value), `as_identifier(...)` (an
   identifier spelling).
2. **Partial selectors** — *where* it may attach, as much or as little as you
   know: `name`, `build_match`, and `owner_match` (the last two are path patterns
   with `.` / `?` / `*` / `+` wildcards).
3. **One-call resolution** — `wire(resource, ...)` runs
   `find_candidates(...)` → `require_one(...)` → `apply(...)` for you and returns
   the resolved candidate. (The three steps stay public if you want them
   separately, and `apply_batch(...)` takes an ordered stream.) `wire` raises a
   diagnostic naming the build path, owner, and source location when the selector
   matches nothing or more than one site.

```python
import astichi
from astichi.assembler import AssemblyScope, as_composable, as_external_value

root = astichi.compile("""
out = []
astichi_hole(body)
result = tuple(out)
""")
body = astichi.compile("""
astichi_pass(out, outer_bind=True).append(astichi_bind_external(label))
""")

scope = AssemblyScope(astichi.build())
scope.add("Root", root)

# One call each, minimal selector — just the demand NAME. No exact target path.
scope.wire(as_composable(body, build_name="Body"), name="body")
scope.wire(as_external_value("done"), name="label")

print(scope.build().materialize().emit(provenance=False))
```

Emitted Python:

```python
out = []
out.append('done')
result = tuple(out)
```

You named the *demand* (`body`, `label`) and nothing else — no
`builder.Root.body.add(...)`, no exact address. The scope found the compatible
hole and the compatible external slot and wired them.

When you *do* need precision — disambiguating among many sites, indexed
instances, ordering — tighten the same call with `build_match` / `owner_match`
path patterns (`.` / `?` / `*` / `+` wildcards), `build_index`, and `order`. That
is also what lets you compose along **two axes at once**: place the *same*
template in many spots (**structure**), and specialize each placement
differently (**substitution**). One template becomes many polymorphic concrete
forms:

```python
import astichi
from astichi.assembler import (
    AssemblyScope, as_composable, as_external_value, as_identifier,
)

shell = astichi.compile("""
class Accessors:
    def __init__(self, data):
        self._data = data
    astichi_hole(methods)
""")

# One polymorphic template: the method name is an identifier demand,
# the lookup key is an external-value slot.
getter = astichi.compile("""
def method_name__astichi_arg__(self):
    return self._data[astichi_bind_external(key)]
""")

scope = AssemblyScope(astichi.build())
scope.add("Shell", shell)

for i, (method, key) in enumerate(
    [("get_name", "name"), ("get_email", "email"), ("get_age", "age")], start=1
):
    inst = f"Getter[{i}]"
    # axis 1 — structure: place the SAME template into `methods`, repeatedly
    scope.wire(as_composable(getter, build_name="Getter", build_index=i, order=i), name="methods")
    # axis 2 — specialization: bind THIS instance's name + key differently
    scope.wire(as_identifier(method), name="method_name", build_match=("Shell", inst))
    scope.wire(as_external_value(key), name="key", build_match=("Shell", inst))

print(scope.build().materialize().emit(provenance=False))
```

Emitted Python — three specialized methods from one template:

```python
class Accessors:

    def __init__(self, data):
        self._data = data

    def get_name(self):
        return self._data['name']

    def get_email(self):
        return self._data['email']

    def get_age(self):
        return self._data['age']
```

That is the polymorphic core: a single template, matched into a hole three
times and specialized per instance — and `as_composable`, `as_identifier`, and
`as_external_value` resources all attached by the same one-call `wire(...)`. YIDL
pushes this to production scale (see [Maturity](#maturity)).

Least-surprise means it never guesses. If a resource fits more than one site,
`wire` refuses (via `require_one`) with a diagnostic that names every candidate's
build path, owner, demand name, kind, and source location, so you know exactly
how to narrow the selector:

```text
ValueError: expected exactly one candidate, found 2
candidate 1:
  demand: build_path=Root owner=. name=first kind=hole.block location=<astichi>:3 locator=body[1]/value
  resource: composable build_name=Frag
    production: name=__block__ kind=production.block location=<astichi>:1 locator=.
candidate 2:
  demand: build_path=Root owner=. name=second kind=hole.block location=<astichi>:4 locator=body[2]/value
  resource: composable build_name=Frag
    production: name=__block__ kind=production.block location=<astichi>:1 locator=.
```

The same matching works **across layers**. A composable you already built can be
registered as a piece of a larger assembly, child scopes resolve before their
parents, and an identifier supplied in one layer can answer a demand in
another — so you compose composables, and astichi keeps the wiring and the
hygiene consistent the whole way up the tree.

Composables carrying `astichi_pyimport(...)` markers also have their imports
auto-linked and deduped at materialize, and the materialization plan tracks both
boundary hygiene and managed-import hygiene so independently authored fragments
never silently collide. Full reference:
**[Assembler Scope](https://github.com/owebeeone/astichi/blob/main/docs/reference/assembler-scope.md)**.

## Native Rust fast path

The target workload is **runtime** code generation — e.g. a class decorator that
assembles a tailored implementation every time it is applied, across many classes
at import time. Pure-Python AST assembly is too slow to sit on that per-use path,
so astichi ships an optional native engine (`_astichi_native_engine`, built with
PyO3) that drives the hot generation path in Rust.

When it is present, lower-engine selection defaults to `auto` and prefers
**native Rust** for the assembler's batch resolve/apply, keeping occurrence/edge
state in the native engine. When the extension is absent, the exact same API runs
on pure Python — native is an accelerator, never a requirement.

- Release wheels bundle the extension; `pip install` from sdist compiles it when
  no matching wheel exists. Set `ASTICHI_SKIP_NATIVE_BUILD=1` for a Python-only
  install.
- Build locally from the repo root with `uv run python native_engine/build.py`.
- `engine=python` remains the differential oracle that the native path is tested
  against.

See **[native_engine/README.md](https://github.com/owebeeone/astichi/blob/main/native_engine/README.md)**
and the perf-refactor notes in
[`dev-docs/`](https://github.com/owebeeone/astichi/tree/main/dev-docs) for the
self-native production boundary.

## Maturity

Astichi is a `1.x` release backed by a suite of **2,250+ tests** — golden
source/plan fixtures, structural snapshots, and integration coverage — run across
CPython 3.12–3.15 and against **both** the Python and native lower engines, with
`engine=python` serving as a differential oracle for the Rust path. Behavior is
anchored by those golden and differential tests; the core
`compile → build → materialize → emit` pipeline is stable, and new surface lands
behind the same test discipline.

**In the wild.** Astichi is the code-generation engine behind **YIDL lifecycle**:
~6,400 lines of declarative `.yidl` across 8 layered concepts compile to **118**
reusable templates and **310** match/contribution rules, which the assembler
weaves into ~4,800 lines of generated lifecycle code — all on both axes (one
template, many specialized placements) plus a concept-inheritance layer on top,
driven through `AssemblyScope`, not by hand. That is the polymorphic, declarative
model above at production scale.

## Documentation

| Topic | Doc |
|-------|-----|
| Docs home | [docs/README.md](https://github.com/owebeeone/astichi/blob/main/docs/README.md) |
| End-to-end guide (compile → emit) | [guide/using-the-api.md](https://github.com/owebeeone/astichi/blob/main/docs/guide/using-the-api.md) |
| Reference index | [reference/README.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/README.md) |
| Glossary | [reference/glossary.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/glossary.md) |
| Public API & submodules | [reference/public-api.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/public-api.md) |
| `compile(...)` | [reference/compile-api.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/compile-api.md) |
| `Composable`, `emit`, `materialize` | [reference/composable-api.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/composable-api.md) |
| Builder (fluent + data-driven) | [reference/builder-api.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/builder-api.md) |
| Descriptors (`describe()`) | [reference/descriptor-api.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/descriptor-api.md) |
| Markers | [reference/marker-overview.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/marker-overview.md) |
| Scoping & hygiene | [reference/scoping-hygiene.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/scoping-hygiene.md) |
| Managed imports | [reference/marker-pyimport.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/marker-pyimport.md) |
| Materialize & emit | [reference/materialize-and-emit.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/materialize-and-emit.md) |
| Assembler scope (auto-attach) | [reference/assembler-scope.md](https://github.com/owebeeone/astichi/blob/main/docs/reference/assembler-scope.md) |
| Implementation snapshot & open gaps | [dev-docs/AstichiSingleSourceSummary.md](https://github.com/owebeeone/astichi/blob/main/dev-docs/AstichiSingleSourceSummary.md) |

## When astichi is *not* the right tool

- You want to refactor or rewrite an existing user codebase — astichi composes
  generator-authored fragments, it is not a generic `ast.NodeTransformer`-style
  codemod or refactoring framework.
- You need a one-off source transform — astichi earns its keep when the same
  generator runs repeatedly (e.g. a decorator applied across many classes) and
  ordering, scope, hygiene, and speed all matter at once.
- A plain string template is genuinely enough and none of those concerns are
  fighting you — you may not need astichi.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv run --with pytest pytest -q
```

Build the native extension (optional): `uv run python native_engine/build.py`.

## License

LGPL-2.1-or-later. See [LICENSE](https://github.com/owebeeone/astichi/blob/main/LICENSE).
</content>
</invoke>
