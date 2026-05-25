use pyo3::prelude::*;
use pyo3::types::PyDict;

pub const VERSION: &str = "0.1.0";
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
        ],
    )?;
    dict.set_item("supported_bundle_schema_versions", vec![1_u32])?;
    dict.set_item("supported_snapshot_schema_versions", vec![1_u32])?;
    dict.set_item("supported_operation_primitives", Vec::<&str>::new())?;
    dict.set_item("artifact_kinds", Vec::<&str>::new())?;
    dict.set_item("parser_backend", crate::parser_ir::PARSER_BACKEND)?;
    dict.set_item("parser_grammar_version", "python-3-compatible")?;
    dict.set_item("parsing_releases_gil", true)?;
    dict.set_item("materialization_releases_gil", false)?;
    Ok(dict.into_any().unbind())
}
