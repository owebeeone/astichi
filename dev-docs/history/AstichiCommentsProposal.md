# Astichi Comments Proposal

Status: implemented in this branch as the design record for comment markers.

Astichi currently emits source from Python ASTs with `ast.unparse`. That keeps
composition structurally safe, but Python comments are not AST nodes, so Astichi
cannot currently generate comments in final emitted code without falling back
to string templating.

This document proposes a statement-only comment marker:

```python
astichi_comment("comment string\nsecond line")
```

The marker is author-facing source syntax, not an executable runtime helper.
It exists only so Astichi can carry comment intent through AST-based
composition until the final output decision is known.

## Problem

Generators often need comments in emitted source for readability,
traceability, or downstream diagnostics:

```python
# generated from schema field: total_cents
out["total_cents"] = int(row["total_cents"])
```

Astichi cannot represent that comment directly in its current AST-only model:

- `ast.parse` discards comments.
- `ast.unparse` cannot emit comments that are not represented in the AST.
- provenance cannot be used to hide comment semantics, because emitted source
  remains authoritative.

The workaround must therefore represent comments as valid Python while Astichi
is still composing, then convert or remove that representation at the final
materialize / emit boundary.

## Goals

- Add one comment marker surface: `astichi_comment("...")`.
- Keep the marker statement-shaped only. It must not produce a value.
- Preserve marker-bearing round-trip before final materialization.
- Render real `#` comments in final emitted source when the caller asks for
  source text.
- Remove comment markers entirely when the caller asks for an executable AST,
  inserting `pass` only where Python syntax needs a non-empty suite.
- Keep comments out of ports, hygiene, descriptors, and provenance semantics.
- Keep final rendered source valid Python.

## Non-Goals

- Do not build a general formatter or custom Python unparser.
- Do not support trailing inline comments in the first version.
- Do not support expression comments such as `value = astichi_comment("x")`.
- Do not evaluate Python to build comment text.
- Do not preserve rendered `#` comments through `compile(...)`; Python parsing
  ignores them, so rendered comments are source text only.
- Do not use provenance as a hidden comment store.
- Do not solve generated-code exception filename repair in this proposal.
  Preserving source filename metadata is useful groundwork for future debug
  emission, but debug exception rewriting is a separate design.

## Public Surface

Valid authored form:

```python
astichi_comment("normalize generated fields")
astichi_comment("line one\nline two")
```

The marker accepts exactly one positional argument, which must be a literal
`str`. It accepts no keyword arguments.

`astichi_comment(...)` is deliberately an exception to the usual
identifier-like marker-argument rule because it is not a name-bearing marker.
Its string is the emitted comment text, not a hole, bind, port, or identifier
reference.

Invalid forms:

```python
value = astichi_comment("no value")
return astichi_comment("no value")
call(astichi_comment("no value"))
astichi_comment(prefix + suffix)
astichi_comment(f"{field}")
astichi_comment(text="no kwargs")
```

Initial recommendation: reject f-strings, variables, concatenation, and bound
external values. A later enhancement can add a compile-time comment-text
evaluator if a concrete generator needs it.

## Source Location Expansion

It is useful for generated comments to point back to the Astichi source that
declared them:

```python
astichi_comment("this comes from {__file__}:{__line__}")
```

Recommended initial expansion names:

- `{__file__}`: the logical source filename from the marker's origin
- `{__line__}`: the 1-based source line of the `astichi_comment(...)` marker

Only the exact substrings `{__file__}` and `{__line__}` are replaced, and every
occurrence is replaced. Replacement is scoped to the literal payload of each
`astichi_comment(...)` marker; Astichi must not do a whole-file text
replacement, because generated Python may legitimately contain those strings in
ordinary code or string literals.

These payload replacements are not Python f-strings and they do not evaluate
arbitrary expressions. They are a comment-marker-only mini-template resolved by
Astichi from source location metadata.

Example rendered output:

```python
# this comes from schema/projector.py:17
```

The file value should come from the `file_name` supplied to
`astichi.compile(...)`. Generators should pass stable logical or repo-relative
filenames if they intend to commit or diff generated output; Astichi should not
invent machine-specific absolute paths.

Because a final composable can merge snippets from multiple source files, the
file cannot be recovered from composable-level `CompileOrigin` alone. Python's
AST stores line and column offsets on nodes, but not filenames. Astichi should
therefore attach a private source-file attribute to parsed AST nodes:

```python
node._astichi_src_file = origin.file_name
```

That metadata should be treated like line/column source location metadata:

- `compile(...)` attaches `_astichi_src_file` to every AST node that already
  represents source from the compiled snippet
- copied or synthesized nodes inherit `_astichi_src_file` from their location
  donor when that donor has one
- comment rendering reads `{__file__}` from the comment marker node's
  `_astichi_src_file`
- comment rendering reads `{__line__}` from the comment marker node's `lineno`;
  no separate line computation is needed, so `compile(..., line_number=...)`
  affects comment expansion exactly as it affects the AST today

Add a helper around `ast.copy_location(...)`, for example:

```python
def copy_astichi_location(target: ast.AST, source: ast.AST) -> ast.AST:
    ast.copy_location(target, source)
    src_file = getattr(source, "_astichi_src_file", None)
    if src_file is not None:
        setattr(target, "_astichi_src_file", src_file)
    return target
```

Then replace direct internal uses of `ast.copy_location(...)` with the helper
where Astichi is preserving source identity. This is broader than comments: it
keeps filename provenance available for future diagnostics and possible debug
emission modes.

Other brace-delimited text passes through unchanged. Only the two exact
placeholder substrings are special:

```python
astichi_comment("kept literally: {field_name}")
```

This renders with `{field_name}` still present. This keeps the first version
intentionally small and avoids creating a second, implicit string-templating
language inside comment payloads.

## API Shape

The key API issue is that one AST cannot both:

- be directly executable with no `astichi_comment(...)` calls, and
- still contain enough information for `.emit()` to render those calls as
  comments.

For that reason, do not make ordinary `.emit()` silently turn comment markers
into `#` comments on pre-materialized composables. Pre-materialize `.emit()`
currently preserves markers so `emit()` -> `compile(...)` round-trips remain
possible; comment markers should follow that rule.

Recommended public split:

```python
executable = composable.materialize()
source = composable.emit_commented()
```

`materialize()` keeps the current executable-AST contract:

- all required state is closed
- hygiene has run
- executable-only markers are gone
- `astichi_comment(...)` is removed
- marker-only non-module suites receive `pass`

`emit_commented(...)` is a peer operation to `materialize()`, not a variant of
ordinary `emit()`. It is the one narrow surface that runs materialization with
comment preservation enabled and then renders those preserved comment markers
as real `#` comments.

Internally, this should be a materialization option/policy:

- normal `materialize()` uses the executable policy and strips comment markers
- `emit_commented(...)` uses the commented-source policy and keeps direct
  `astichi_comment(...)` statements long enough to render them as comments
- the commented-source policy inserts `pass` after comments where a suite would
  otherwise be empty
- `emit_commented(...)` has no `provenance=` parameter and does not append a
  provenance trailer

This avoids putting comment rendering into ordinary `emit()`, and it avoids
making `.materialize().emit()` depend on hidden comment side data that is no
longer in the materialized AST.

If later API variants are needed, represent the output choice with
behavior-bearing policy objects rather than string tags or enums.

## Rendering Semantics

Each payload line becomes one Python comment line at the marker statement's
indentation:

```python
astichi_comment("line one\nline two")
```

renders as:

```python
# line one
# line two
```

Empty payload lines render as bare `#` lines:

```python
astichi_comment("before\n\nafter")
```

renders as:

```python
# before
#
# after
```

The payload is raw comment text. Authors should not include the leading `#`.
If they do, Astichi should not strip it; the output will contain the extra
character intentionally.

Line ending handling should normalize `\r\n` and `\r` to `\n` before rendering.

## Empty Suite Semantics

Comments are not executable statements. If comment removal would leave a
non-module suite empty, Astichi must synthesize `pass`.

Input:

```python
if enabled:
    astichi_comment("nothing to do")
```

Executable materialization:

```python
if enabled:
    pass
```

Comment-rendered source:

```python
if enabled:
    # nothing to do
    pass
```

For multiline payloads in an otherwise empty suite, every rendered comment line
uses the same indentation as the original marker statement, and the synthetic
`pass` follows at that same suite indentation:

```python
if enabled:
    astichi_comment("nothing to do\nhere")
```

renders as:

```python
if enabled:
    # nothing to do
    # here
    pass
```

At module level, no synthetic `pass` is required. A file containing only
comments is valid Python and reparses to an empty module body.

The suite logic should reuse the existing empty-suite behavior currently used
when residual markers are stripped from functions, classes, `if`, loops,
`try`, exception handlers, `match` cases, and similar statement bodies.

## Composition Semantics

`astichi_comment(...)` has no ports and creates no bindings. It should not
appear in `describe()` output except possibly through future source-location
debug metadata.

It should compose like an inert block statement:

- additive block insertion preserves its relative order
- nested build stages preserve it until finalization
- unrolling repeats it if it appears inside an `astichi_for(...)` body
- hygiene ignores it
- boundary import/pass/export logic ignores it

The marker should be valid anywhere a normal statement is valid inside an
Astichi-owned body, including module, function, class, branch, loop, and
inserted block bodies.

## Comment Placement

Comment markers render comments at the same source location where the
`astichi_comment(...)` statement appears. Astichi should not move comments to
protect docstrings, future imports, managed imports, or marker prefixes.

The authored marker order is the rendered comment order:

```python
astichi_comment("generated file")
"""Module docstring."""
from __future__ import annotations
```

renders as:

```python
# generated file
"""Module docstring."""
from __future__ import annotations
```

The rendered comment is a real Python comment, so it does not prevent the
following string literal from being a module docstring. In marker-preserving
round-trip source, Astichi owns the marker-bearing AST and should not assign
extra semantics to comments before docstrings beyond normal marker handling.

## Provenance And Round Trip

There are two different round-trip stories:

- Marker-preserving emit:
  `composable.emit()` should keep `astichi_comment("...")` in source, so
  `compile(emitted, source_kind="astichi-emitted")` can reconstruct the same
  marker-bearing AST. Ordinary `emit()` remains the round-trip surface for all
  Astichi markers.
- Final comment-rendered emit:
  `emit_commented(...)` should output real `#` comments. Recompiling that
  source cannot reconstruct `astichi_comment(...)`, because Python discards
  comments. That is acceptable because this is final source output.
  `emit_commented(...)` intentionally has no provenance mode; callers that need
  marker-preserving round-trip source should use ordinary `emit(...)`.

## Implementation Sketch

Likely implementation areas:

- `src/astichi/lowering/markers.py`
  - add a `_CommentMarker` with `source_name = "astichi_comment"`
  - validate exactly one literal string positional argument
  - contribute no demand or supply ports
- `src/astichi/frontend/api.py`
  - reject comment markers whose inferred shape is not block
  - keep comment markers accepted in authored source
- `src/astichi/materialize/api.py`
  - add an execution cleanup pass that removes comment marker statements
  - reuse empty-suite `pass` insertion for marker-only suites
  - add an internal materialization option/policy for the comment-preserving
    branch used by `emit_commented`
- `src/astichi/ast_provenance.py`
  - add `_astichi_src_file` attachment and propagation helpers
  - add an `ast.copy_location(...)` wrapper that copies line/column location
    and Astichi's private source-file attribute together
  - migrate existing internal `ast.copy_location(...)` calls to the wrapper
    where the source donor should remain visible downstream
- `src/astichi/model/basic.py`
  - expose `emit_commented(...)` as the public peer to `materialize()`
  - delegate to the comment-preserving materialization option rather than to
    ordinary `.emit()`
- `src/astichi/emit/api.py`
  - keep ordinary `emit_source(...)` marker-preserving
  - provide only the low-level comment rendering helper if that is useful for
    the materialization branch
- `tests/data/gold_src/support/golden_case.py`
  - add an option that writes materialized output through `emit_commented(...)`
    instead of ordinary executable `materialized.emit(...)` for comment-rendered
    golden cases
- `docs/reference/`
  - document the marker, finalization split, and round-trip limitations

The source rendering filter should not use a blind text regex. A safer shape is:

1. unparse the renderable materialized tree that still contains direct
   `astichi_comment(...)` statements
2. parse the unparsed source back to locate direct whole-statement comment
   marker calls by line span
3. replace only those statement spans with rendered `#` lines using the
   parsed statement indentation

This keeps replacements out of string literals and unrelated identifiers.

## Test Plan

Use canonical golden/source fixtures for successful final source behavior:

- simple top-level comment renders as `# ...`
- multiline comment renders as multiple `#` lines
- comment inside inserted block preserves order around generated statements
- comment-only function/class/branch body renders comments plus `pass`
- comment-only module renders comments without synthetic `pass`
- comments around module docstrings and future imports render at the marker
  locations without reordering
- pre-materialize `emit()` preserves `astichi_comment(...)`
- final rendered source parses as executable Python and has no provenance tail

Use focused tests for validation and cleanup mechanics:

- expression-position comment marker rejects
- non-string payload rejects
- keyword arguments reject
- f-string payload rejects
- execution materialization strips comment markers from `.tree`
- no `astichi_comment(...)` survives executable `.materialize().emit()`
- rendered-source filter does not replace `astichi_comment` text inside string
  literals
- `{__file__}` and `{__line__}` replace all exact occurrences in a comment
  payload, but do not affect other source text
- merged snippets from different `file_name` origins render the correct file
  for each comment marker
- synthesized nodes copied from donors preserve `_astichi_src_file` through the
  new copy-location helper

## Open Questions

- Should dynamic comment text be supported later?
  - Initial recommendation: not until there is a concrete generator need. If
    added, reuse a restricted compile-time evaluator rather than executing
    arbitrary Python.
- Should comments become descriptor-visible metadata?
  - Initial recommendation: no. Comments are output text, not composition
    surfaces.
- Should future debug emission use `_astichi_src_file` to improve exception
  filenames in generated code?
  - Deferred. The source-file propagation mechanism is useful groundwork, but
    exception rewriting or line-level wrappers need a separate design.
