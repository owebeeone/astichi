use pyo3::prelude::*;
use pyo3::types::PyModule;

mod capabilities;
mod engine;
mod errors;
mod handles;
mod surface_registry;

#[pyfunction]
fn version() -> &'static str {
    capabilities::VERSION
}

#[pyfunction(name = "capabilities")]
fn capabilities_py(py: Python<'_>) -> PyResult<Py<PyAny>> {
    capabilities::snapshot(py)
}

#[pyfunction]
fn self_test(py: Python<'_>) -> PyResult<bool> {
    let mut handle = engine::create(py, None)?;
    handle.snapshot_dict(py)?;
    handle.close();
    Ok(true)
}

#[pymodule]
fn _astichi_native_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(capabilities_py, m)?)?;
    m.add_function(wrap_pyfunction!(self_test, m)?)?;
    engine::register_module_functions(m)?;
    surface_registry::register_module_functions(m)?;
    Ok(())
}
