use pyo3::prelude::*;
use pyo3::types::PyDict;

pub const VERSION: &str = "1.0.2";
pub const ABI_SCHEMA_VERSION: u32 = 1;
pub const BACKEND_LABEL: &str = "rust-pyo3-core";

pub fn snapshot(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("abi_schema_version", ABI_SCHEMA_VERSION)?;
    dict.set_item("version", VERSION)?;
    dict.set_item("backend_label", BACKEND_LABEL)?;
    dict.set_item("build_profile", "cargo release")?;
    dict.set_item(
        "engine_features",
        vec![
            "native.extension.v1",
            "native.engine_core.v1",
            "native.parser_ir.v1",
            "native.surface_registry.v1",
            "native.pattern_registry.v1",
            "native.template_snapshot.empty.v1",
            "native.template_extract.direct_call.v1",
            "native.template_extract.identifier_suffix.v1",
            "native.template_extract.payload.v1",
            "native.template_extract.insert_metadata.v1",
            "native.occurrence_store.v1",
            "native.record_indexes.v1",
            "native.candidate_query.v1",
            "native.overlay_store.v1",
            "native.materialization_operation_stream.v1",
            "native.materialization_overlay_stream.v1",
            "native.materialization_workspace.v1",
            "native.materialization_expression.v1",
            "native.materialization_block.v1",
            "native.materialization_parameters.v1",
            "native.materialization_call_arguments.v1",
            "native.materialization_identifier_overlay.v1",
            "native.materialization_literal_ref.v1",
            "native.materialization_external_overlay_literal.v1",
            "native.hygiene_gate.v1",
            "native.artifact_builder.python_ast.baseline.v1",
            "native.lower_template_package_v2.snapshot.partial.v1",
            "native.lower_template_package_v2.v1",
            "native.full_lower_engine.current_surfaces.v1",
        ],
    )?;
    dict.set_item("supported_bundle_schema_versions", vec![1_u32])?;
    dict.set_item("supported_snapshot_schema_versions", vec![1_u32])?;
    dict.set_item("supported_operation_primitives", Vec::<&str>::new())?;
    dict.set_item("artifact_kinds", vec!["python_ast"])?;
    dict.set_item("parser_backend", crate::parser_ir::PARSER_BACKEND)?;
    dict.set_item("parser_grammar_version", "python-3-compatible")?;
    dict.set_item("parsing_releases_gil", true)?;
    dict.set_item("materialization_releases_gil", false)?;
    Ok(dict.into_any().unbind())
}
