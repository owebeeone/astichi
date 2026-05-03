# Astichi Build Resolver Proposal

Status: proposal.

This document proposes a build-resolution layer that separates "available
source fragments" from "output roots". The motivating case is YIDL generation:
YIDL wants to register a vocabulary of precompiled Astichi composables once,
then select the fragments needed for one generated shape without hand-tracking
which unused fragments still contain unresolved holes or binds.

## Problem

Astichi currently uses `builder.add.<Name>(piece)` for two related but distinct
roles:

- register a named instance so edges can refer to it as a source
- make that instance root-capable in the final build

Current `build_merge(...)` preserves compatibility by emitting every registered
instance that is not consumed as an additive-edge source. That is correct for
multi-root authored builds:

```python
builder.add.RootA(piece_a)
builder.add.RootB(piece_b)
```

But it is the wrong shape for generator palettes:

```python
builder.add.Root(record_class_shell)
builder.add.RequiredParam(required_param_template)
builder.add.DefaultedParam(defaulted_param_template)
```

If a particular record uses only required parameters, the unused defaulted
parameter template still remains an unconsumed registered instance. Because it
contains unresolved state such as `default_path`, it becomes either an emitted
root with unresolved markers or a materialize-time error. YIDL then has to add
manual conditional registration logic, even though the real intention is simply:
"these are available templates; only inserted templates are live."

That complexity belongs in Astichi, not in every generator built on Astichi.

## Goal

Add an explicit source-definition surface and a build resolver:

- root-capable instances remain the public output surface
- source-only definitions are inert until reached by an edge from a live root
- unresolved demands inside unused source-only definitions are ignored
- unresolved demands inside live definitions still reject normally
- existing `builder.add` multi-root behavior remains compatible

## Non-goals

- Do not make all unused `builder.add` instances inert. That would break the
  current contract where unconsumed added instances become output roots.
- Do not introduce optional holes as a hidden workaround. Optional holes may be
  useful later, but they are a separate source-shape feature.
- Do not weaken materialize gates. Live unresolved holes, external binds,
  identifier demands, and parameter holes must still reject.
- Do not store hidden semantic state in provenance.

## Public API Shape

Keep `builder.add` as the root-capable registration surface:

```python
builder.add.Root(root_shell)
```

Add a source-only definition surface:

```python
builder.define.RequiredParam(required_param_template)
builder.define.DefaultedParam(defaulted_param_template)
```

Data-driven equivalents must exist because YIDL should not rely on fluent
attribute synthesis:

```python
builder.define("RequiredParam", required_param_template)
builder.define("DefaultedParam", defaulted_param_template)
```

Defined instances are still valid edge sources:

```python
builder.Root.params.add.RequiredParam(order=0)
builder.Root.params.add("DefaultedParam", order=1, bind={"default_path": path})
```

The existing target-adder overlays continue to apply:

```python
builder.Root.params.add.RequiredParam(
    order=0,
    arg_names={"field_name": "count"},
    keep_names=["count"],
)
```

## Internal Model

Add an instance placement concept to the builder graph. It should be a semantic
object, not a string tag or enum. It needs behavior equivalent to:

- root-capable: may become a final output root
- source-only: may be used by edges but is not a final output root by itself

`builder.add` creates root-capable records. `builder.define` creates
source-only records. Both records share the same source-addressing behavior for
edges, descriptor wiring, overlays, and path resolution.

## Build Resolver

Insert a resolver step at the start of `build_merge(...)`.

Inputs:

- builder graph instances
- additive edges
- explicit assign/bind_identifier records
- unroll option

Outputs:

- live instance records
- live additive edges
- output root names

The resolver should:

1. Determine output roots.
   - Start with root-capable instances not consumed as additive-edge sources.
   - Preserve current fallback behavior when every root-capable instance is
     consumed: use edge target roots.
   - Never include source-only definitions as output roots just because they are
     unconsumed.
2. Compute the live closure.
   - Start from output roots.
   - Include every edge whose target root is live.
   - Include each edge's source instance.
   - Repeat, because a live source may itself be a target of other edges.
3. Filter the graph view passed to merge/materialize.
   - Live source-only definitions participate normally.
   - Unused source-only definitions are invisible to port validation,
     materialize gates, emitted output, provenance, and root wrapping.
4. Keep diagnostics sharp.
   - Referencing an unknown source still rejects when the edge is added.
   - A live source with unresolved required state rejects at materialize.
   - An unused source-only definition with unresolved state does not reject.

This keeps the existing graph records simple while moving "what is actually
part of this build?" into one explicit resolver.

## Demand and Supply Semantics

Demand and supply validation must use the resolved live graph, not the raw
registered palette.

Consequences:

- unused source-only supply ports must not satisfy descriptors
- unused source-only demand ports must not create mandatory unresolved work
- live edge-specialized sources must validate after edge overlays are applied
- provenance and `emit()` should describe only the built result, not the
  unused palette

This matches source authority: the emitted program contains only the resolved
build, and recompiling emitted source cannot recover unused source definitions.

## YIDL Record-Class Example

YIDL should be able to precompile and define all reusable fragments once:

```python
generator.define("RecordClass", record_class_shell)
generator.define("SlotItem", slot_item_expr)
generator.define("RequiredParam", required_param_payload)
generator.define("DefaultedParam", defaulted_param_payload)
generator.define("InitAssign", init_assign_stmt)
```

A particular record build can then wire only what it needs:

```python
builder.add.Root(generator.RecordClass)
builder.Root.slot_items.add.SlotItem(...)
builder.Root.params.add.RequiredParam(...)
```

If no field has a default, `DefaultedParam` remains an unused source-only
definition. Its unresolved `default_path` demand is ignored because it is not
in the live closure.

## Implementation Notes

Likely files:

- `src/astichi/builder/graph.py`
  - add instance placement concept
  - add source-only registration
- `src/astichi/builder/handles.py`
  - add fluent and named `builder.define` surface
  - preserve existing `builder.add` behavior
- `src/astichi/materialize/api.py`
  - add build resolver before instance refresh/unroll/edge grouping
  - run existing merge logic against the resolved live graph view
- `docs/reference/builder-api.md`
  - document root-capable vs source-only registration
- `dev-docs/AstichiSingleSourceSummary.md`
  - update after implementation, not while this remains only a proposal

Avoid spreading liveness checks through materialization. The resolver should
produce a graph view that existing downstream logic can mostly consume as if it
were the original graph.

## Test Plan

Use goldens for success behavior where practical:

- source-only unused definition with unresolved external bind is ignored
- source-only unused definition with unresolved hole is ignored
- source-only definition used by an edge must satisfy all required demands
- source-only definition can itself be a target of another edge and remains
  live through closure
- `builder.add` multi-root behavior remains unchanged
- data-driven `builder.define("Name", piece)` matches fluent
  `builder.define.Name(piece)`

Use focused tests for failure/diagnostic mechanics:

- duplicate source-only definition name rejects like duplicate `builder.add`
- edge to unknown source-only name rejects
- source-only definition cannot be selected as an output root accidentally
- live source-only unresolved bind reports the source instance clearly

## Open Questions

- Should source-only definitions be addressable through `builder.Instance` for
  target paths, or only through target-adder source selection?
  - Initial recommendation: yes, allow normal handles. A source-only definition
    can be a live intermediate target once a root reaches it.
- Should `builder.define` accept `arg_names` and `keep_names`?
  - Initial recommendation: yes. It should share registration behavior with
    `builder.add`, except for output-root eligibility.
- Should `builder.build(root=...)` be added later?
  - Possibly, but it is not required for this proposal. The immediate issue is
    unused palette definitions, not manual root selection.

