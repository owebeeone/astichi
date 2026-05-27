# F3a — Compile parity ledger and test map

Status: tag `rust-fsn/f3a-compile-ledger`.

Source of truth: `astichi/src/astichi/frontend/api.py` `compile()`.

## Parse and origin

| Step | Python today | Native target (F3b+) | Primary tests |
|------|----------------|----------------------|---------------|
| Line/offset padding | `_padded_source`, `apply_offset` | Same text fed to rustpython | `test_compile_*` goldens, parser_ir gold |
| `ast.parse` | Required | Remove on success path (F3d) | `test_native_engine_parser_ir.py`, gold_src |
| Indentation retry | Second parse without offset | Native grammar policy | ad hoc syntax errors |
| `attach_astichi_source_file` | Python walk | Native locator policy | structural goldens |
| `source_kind` normalization | `normalize_source_kind` | Native gate | emitted vs authored tests |

## Validation gates (pre-inventory)

| Step | Function | Native (F3b) | Tests |
|------|----------|----------------|-------|
| Authored `astichi_insert` ban | `_validate_authored_marker_surface` | native IR | emitted source_kind tests |
| Boundary marker placement | `validate_boundary_marker_placement` | native IR | `test_boundary_*`, gold_src |
| Call-arg payload surface | `validate_call_argument_payload_surface` | native IR | `test_call_argument_payload_recognition.py` |
| Parameter payload surface | `validate_parameter_payload_surface` | native IR | `test_parameter_holes.py` |
| External ref desugar | `desugar_external_ref_kwargs` | native IR | ref/payload goldens |
| External ref surface | `validate_external_ref_surface` | native IR | `test_*ref*` |
| Marker recognition | `recognize_markers` | native template extract | gold_src, structural |
| Comment markers | `_validate_comment_markers` | native IR | `comment_marker.py` golden |
| Pyimport declarations | `validate_pyimport_declarations` | native IR | pyimport goldens |
| Parameter holes | `validate_parameter_hole_surface` | native IR | `test_parameter_holes.py` |
| Boundary interaction matrix | `validate_boundary_interaction_matrix` | native IR | boundary tests |
| `keep_names` param | `_validate_keep_names` | native (metadata) | compile keep tests |
| Name analysis | `analyze_names` | native projection (F3b) | hygiene tests |
| Demand/supply ports | `extract_demand_ports`, `extract_supply_ports` | native package v2 | `test_lower_engine_compile_route.py` |
| `arg_names` eager bind | `_validate_arg_names` + `bind_identifier` | native (F2b) | compile route, bind tests |

## Lower registration

| Path | Behavior | Native today | Tests |
|------|----------|--------------|-------|
| Python engine | `register_inventory_template(tree=...)` | N/A | python matrix goldens |
| Native engine | `register_native_template_source_direct(source, tree)` | Package v2 + duplicate parse | `test_compile_explicit_native_*` |
| Backend assert | `_assert_selected_native_backend` | Yes | compile route native tests |

## Capability gate

| Capability | When |
|------------|------|
| `native.self_native.compile_validation.v1` | F3b complete |
| `native.self_native.no_python_parse_compile.v1` | F3d |

## F3c differential scope

For each ledger row marked **native IR** in F3b, add paired `engine=python` vs
`engine=native` tests: same source, same success/failure class, diagnostic
location strict / message loose (plan §F3c).

## F3d swap checklist

- [ ] Native validators cover all authored-surface rows above
- [ ] F3c differential green on `tests/data/gold_src/`
- [x] `python_compile_ast_parse` counter zero on lifecycle import (F3d)
- [x] Advertise `no_python_parse_compile.v1` (F3d)
