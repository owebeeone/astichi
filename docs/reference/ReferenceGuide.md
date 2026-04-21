# Astichi reference guide (snippets)

Condensed map: each **topic** is a directory under [`snippets/`](snippets/). **Authored** sources are `*.py` (optional `# astichi-snippet: {…}` metadata), **builder bundles** (`snippet.json` + parts), or **`recipe.py`** (multi-stage / non-JSON wiring). **Materialized** output is **`*_generated.py`** in the **same directory** as the authored file: flat `foo.py` → `foo_generated.py`; bundle directory `bar/` → `bar/bar_generated.py`. Do not edit by hand.

**Regenerate:** from the `astichi/` tree, run  
`uv run python scripts/generate_reference_snippet_outputs.py`

**API:** `astichi.compile` → optional `.bind` / `.bind_identifier` → `.materialize()`; builder bundles use `astichi.build()`, `add`, `assign`, `build(unroll=…)`.

| Topic | Forms covered | Authored | Materialized (sibling `*_generated.py`) |
| --- | --- | --- | --- |
| **bind_external** | tuple binding; mapping-style `bind` kwargs | [tuple_binding.py](snippets/bind_external/tuple_binding.py), [mapping_binding.py](snippets/bind_external/mapping_binding.py) | [tuple_binding_generated.py](snippets/bind_external/tuple_binding_generated.py), [mapping_binding_generated.py](snippets/bind_external/mapping_binding_generated.py) |
| **ref** | string literal path; `external=` + `bind`; f-string + bound prefix; subscript into bound tuple; transparent one-shot sentinel `astichi_v` / `_` | [ref/](snippets/ref/) | e.g. [literal_generated.py](snippets/ref/literal_generated.py); same suffix pattern for other `ref/*.py` |
| **unroll** | `astichi_for` + ref in loop body (`unroll=True`) | [unroll/for_literal_ref/](snippets/unroll/for_literal_ref/) | [for_literal_ref_generated.py](snippets/unroll/for_literal_ref/for_literal_ref_generated.py) |
| **keep** | call-form `astichi_keep` | [call_keep.py](snippets/keep/call_keep.py) | [call_keep_generated.py](snippets/keep/call_keep_generated.py) |
| **keep_identifier** | `__astichi_keep__` class/def suffix | [class_suffix.py](snippets/keep_identifier/class_suffix.py) | [class_suffix_generated.py](snippets/keep_identifier/class_suffix_generated.py) |
| **arg** | `__astichi_arg__` resolved via `bind_identifier` | [resolved.py](snippets/arg/resolved.py) | [resolved_generated.py](snippets/arg/resolved_generated.py) |
| **export** | `astichi_export` (supply port; marker stripped) | [export_line.py](snippets/export/export_line.py) | [export_line_generated.py](snippets/export/export_line_generated.py) |
| **import** | `astichi_import`; explicit builder / `arg_names` threading; same-name immediate outer bind via `outer_bind=True` | [import/accumulator_step/](snippets/import/accumulator_step/) | [accumulator_step_generated.py](snippets/import/accumulator_step/accumulator_step_generated.py) |
| **pass** | value-form only: walrus RHS `(x := astichi_pass(y))`, direct value / call / attribute use, transparent one-shot sentinel `astichi_v` / `_`, and same-name immediate outer bind via `outer_bind=True`; bare statement-form `astichi_pass(...)` rejects | [pass/if_walrus_pass/](snippets/pass/if_walrus_pass/) | [if_walrus_pass_generated.py](snippets/pass/if_walrus_pass/if_walrus_pass_generated.py) |
| **funcargs** | **`*` hole:** ordered positional payloads; **`**` hole:** keyword payloads + edge order; **call hole + fixed keywords:** `func(hole, fixed=…)` with payload `first, named=…, **extra`; **walrus + boundary markers:** `(out := seed)`, `_=astichi_import(seed)`, `_=astichi_export(out)` with `assign` wiring; **same** with `compile(..., arg_names=…)` on the fragment instead of `assign`; **`astichi_pass`** as the walrus RHS; **`astichi_bind_external`** in the carrier + `.bind()` before materialize | [funcargs/](snippets/funcargs/) (`ordered_variadic/`, `named_variadic_kwargs/`, `plain_fixed_keywords_star_extra/`, `walrus_import_export_assign/`, `payload_compile_arg_names/`, `pass_walrus_export/`, `bind_external_arg/`) | e.g. [ordered_variadic_generated.py](snippets/funcargs/ordered_variadic/ordered_variadic_generated.py); each subfolder has a matching `*_generated.py` |
| **expr** | scalar expression hole + single insert | [expr/scalar_hole/](snippets/expr/scalar_hole/) | [scalar_hole_generated.py](snippets/expr/scalar_hole/scalar_hole_generated.py) |
| **statement** | block hole + builder-generated insert synthesis | [statement/block_hole/](snippets/statement/block_hole/) | [block_hole_generated.py](snippets/statement/block_hole/block_hole_generated.py) |
| **composition** | **Staged graphs:** first `build()` produces a composable embedded in a later `build()`; **unroll on a subsequent `build(unroll=True)`** after indexed edges onto a loop carried in from the prior merge | [composition/staged_unroll_indexed_edges/](snippets/composition/staged_unroll_indexed_edges/) ([recipe.py](snippets/composition/staged_unroll_indexed_edges/recipe.py)), [composition/nested_three_stage_trace/](snippets/composition/nested_three_stage_trace/) | [staged_unroll_indexed_edges_generated.py](snippets/composition/staged_unroll_indexed_edges/staged_unroll_indexed_edges_generated.py), [nested_three_stage_trace_generated.py](snippets/composition/nested_three_stage_trace/nested_three_stage_trace_generated.py) |
| **scope** | **Hygiene / names:** colliding locals across two inserts (`total` -> `total__astichi_scoped_*`); **two named holes** (`setup` then `body`); **builder insert + `astichi_keep`** (inner `value` renamed, outer name kept) | [scope/](snippets/scope/) | [colliding_locals_two_inserts_generated.py](snippets/scope/colliding_locals_two_inserts/colliding_locals_two_inserts_generated.py), [two_holes_ordered_generated.py](snippets/scope/two_holes_ordered/two_holes_ordered_generated.py), [outer_hole_inner_insert_keep_generated.py](snippets/scope/outer_hole_inner_insert_keep/outer_hole_inner_insert_keep_generated.py) |

**Metadata line** (optional, first line of a flat snippet):

`# astichi-snippet: {"bind": {...}, "bind_identifier": {...}, "arg_names": {...}}`

JSON lists in `bind` are normalized to tuples where needed.

**Builder bundle** (`snippet.json`):

- `instances`: map of **builder instance name** → fragment filename **or** `{ "file": "impl.py", "arg_names": { … } }` (any `astichi.compile` kwargs).
- `wires`: Python expressions evaluated with `builder` in scope (e.g. `builder.Root.body.add.Step1(...)`).
- `unroll`: passed to `build(unroll=…)`.

**Recipe bundle** (`recipe.py` only, no `snippet.json`):

- Defines **`def run() -> str:`** returning **`ast.unparse(...materialize().tree)`**.
- Use when the example needs **multiple `build()` calls**, **`assign` chains**, or **indexed `Pipeline.Root.Loop.step[i]`** wiring that is awkward to encode as JSON.

Long-form narrative docs: [marker-overview.md](marker-overview.md), [using-the-api.md](../guide/using-the-api.md), [addressing.md](addressing.md) (paths + indexed edges).
