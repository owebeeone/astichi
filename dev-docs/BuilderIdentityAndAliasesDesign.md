# Builder identity, ref paths, and deferred **aliases**

Status: **design note** — ref-path behaviour is **implemented**; **aliases** are
**not** implemented and are the recommended follow-on for multi-stage compose.

## 1. What exists today (implemented)

### 1.1 Named root instances on the graph

After `builder.add.<Name>(piece)`, the same graph exposes **stable root
identifiers** by instance name:

- `builder.<Name>` → `InstanceHandle` for any registered root (must already
  exist in `BuilderGraph`).

Tests: `tests/test_builder_handles.py` (`test_builder_root_instance_lookup_*`).

### 1.2 Fully-qualified `assign` with nested shell paths

`builder.assign.<Src>...to().<Dst>...` is not limited to “root of instance ×
bare identifier”. `AssignBinding` carries optional `source_ref_path` and
`target_ref_path` (`RefPath` tuples) so the demand site and supplier can be
addressed along **nested insert / hole structure** inside a piece, not only at
the instance root.

Implementation: `src/astichi/builder/handles.py` (`_AssignSourcePicker`,
`_AssignSourceReady`, `_AssignTargetHandle`), `src/astichi/builder/graph.py`
(`AssignBinding`), resolved in `build_merge` / `_apply_assign_bindings`.

This fixes an important expressiveness gap: you can point at “interesting” sites
in the **builder graph** using a path that matches the **composition structure**
of contributions.

## 2. Why this is not yet “stable identity across stages”

Multi-staged composition reuses composables produced by an earlier
`build()` / `materialize()` / `emit()` round trip (or attaches new instances to
an evolving graph). Several forces make **raw paths and Python identifiers**
a weak primary identity:

1. **Hygiene renames** lexical names for collision safety (`__astichi_scoped_*`,
   trust model, etc.). A name that reads well in stage *n* is not guaranteed to
   survive unchanged after merge + materialize in stage *n+1*.

2. **AST-graph path alone** as an identifier ties “who this is” to **the shape
   of the resulting inlined tree** (which inserts exist, order, unroll). That
   couples build intent to emergent structure — hard to reason about and brittle
   when the tree changes without a semantic change.

3. **Ref paths** are stable relative to **declared insert shell structure** in a
   given composable, but they are still **positional addressing** into that
   structure, not a first-class **named** handle that survives arbitrary
   pipeline stages unless we add an explicit layer.

So: today’s ref paths are the right **mechanism inside one build graph**; they
are not yet a **durable, user-facing identity** for cross-stage reasoning.

## 3. Deferred feature: **aliases** (recommended direction)

**Goal:** allow the author to associate a **stable logical name** with a
**fully-qualified build reference** (instance + ref path + role as needed), so
that:

- the same alias can be used across **multiple** build stages;
- stage *n+1* does not need to track hygiene output or raw AST paths as the
  primary key;
- “interesting” graph references **survive** a build stage as first-class data on
  the graph or composable, not as ephemeral fluent-chain state only.

**Sketch (not an API commitment):**

- `BuilderGraph` (or a sibling registry) holds `alias → ResolvedBuildRef` where
  `ResolvedBuildRef` captures everything `assign` needs today (`instance`,
  `ref_path`, slot kind, …) without encoding it as a Python identifier string
  from emitted source.
- Fluent surface might look like `builder.alias("acc_total").binds(...)` or be
  limited to raw API first.
- Materialize may **resolve** aliases to concrete ports/occurrences at a fixed
  phase; hygiene must never be the only name stable users see for cross-stage
  linking.

**Relationship to existing surfaces:**

- **`keep_names` / trust** — about **lexical** spelling in emitted Python.
- **Aliases** — about **composition graph** identity across stages; orthogonal
  but composable (e.g. an alias might point at a port that is also keep-pinned).

## 4. Where implementation should land (when aliases ship)

| Concern | Owner |
|---------|--------|
| Storage of alias → build ref | `builder/graph.py` or dedicated module imported by it |
| Validation (reachable path, non-conflicting bindings) | `build_merge` gate or pre-merge pass |
| Fluent API | `builder/handles.py` |
| Multi-stage tests | `tests/test_builder_*.py`, staged scenarios in `AstichiV3TestPlan.md` |

Ref-path `assign` remains the low-level primitive; **aliases** sit above it as
stable named indirection.

## 5. Documentation map

| Document | Role |
|----------|------|
| `AstichiSingleSourceSummary.md` §3.2 | **Canonical crisp** summary: graph ids, `assign` ref paths, names vs identity, deferred aliases |
| **This file** | Optional expansion: extra rationale, sketch API, implementation owners |
| `AstichiV3TestPlan.md` | Spine tests for staged compose; extend when aliases exist |
| `BoundaryScopePolicyProposal.md` | Orthogonal: **seal/join** at hole/insert boundaries |

## 6. Summary

- **Now:** root lookup by name + `assign` with `source_ref_path` /
  `target_ref_path` — sufficient for rich wiring **within one builder graph**.
- **Next (aliases):** stable named indirection over fully-qualified build
  references so **multi-stage** compose does not depend on hygiene-changed
  identifiers or fragile AST-path-only identity.
