use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};

const VERSION: &str = "0.1.0";
const ABI_SCHEMA_VERSION: u32 = 1;
const BACKEND_LABEL: &str = "rust-pyo3-skeleton";

#[pyfunction]
fn version() -> &'static str {
    VERSION
}

#[pyfunction]
fn capabilities(py: Python<'_>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);
    dict.set_item("abi_schema_version", ABI_SCHEMA_VERSION)?;
    dict.set_item("version", VERSION)?;
    dict.set_item("backend_label", BACKEND_LABEL)?;
    dict.set_item("build_profile", "cargo release")?;
    dict.set_item("engine_features", Vec::<&str>::new())?;
    dict.set_item("supported_bundle_schema_versions", vec![1_u32])?;
    dict.set_item("supported_snapshot_schema_versions", vec![1_u32])?;
    dict.set_item("supported_operation_primitives", Vec::<&str>::new())?;
    dict.set_item("artifact_kinds", Vec::<&str>::new())?;
    dict.set_item("parser_backend", py.None())?;
    dict.set_item("parser_grammar_version", py.None())?;
    dict.set_item("parsing_releases_gil", false)?;
    dict.set_item("materialization_releases_gil", false)?;
    Ok(dict.unbind())
}

#[pyfunction]
fn self_test() -> bool {
    true
}

#[pymodule]
fn _astichi_native_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(capabilities, m)?)?;
    m.add_function(wrap_pyfunction!(self_test, m)?)?;
    Ok(())
}
