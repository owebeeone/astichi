use std::sync::atomic::{AtomicU64, Ordering};

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};

use crate::handles::{EngineHandle, HandleKind};

static NEXT_OWNER_ID: AtomicU64 = AtomicU64::new(1);

#[pyfunction(name = "engine_create", signature = (request=None))]
pub fn create(py: Python<'_>, request: Option<Py<PyAny>>) -> PyResult<EngineHandle> {
    if let Some(request) = request {
        let request = request.bind(py);
        if !request.is_none() && !request.is_instance_of::<PyDict>() {
            return Err(crate::errors::schema_error(
                "engine_create request must be a dict or None",
            ));
        }
    }
    let owner_id = NEXT_OWNER_ID.fetch_add(1, Ordering::Relaxed);
    Ok(EngineHandle::new(owner_id))
}

#[pyfunction(name = "engine_close")]
pub fn close(mut handle: PyRefMut<'_, EngineHandle>) -> PyResult<()> {
    handle.ensure_open()?;
    handle.close();
    Ok(())
}

#[pyfunction(name = "engine_snapshot")]
pub fn snapshot(py: Python<'_>, handle: PyRef<'_, EngineHandle>) -> PyResult<Py<PyAny>> {
    handle.ensure_open()?;
    handle.snapshot_dict(py)
}

#[pyfunction(name = "engine_assert_same_owner")]
pub fn assert_same_owner(
    left: PyRef<'_, EngineHandle>,
    right: PyRef<'_, EngineHandle>,
) -> PyResult<bool> {
    left.ensure_open()?;
    right.ensure_open()?;
    if left.owner_id() != right.owner_id() {
        return Err(crate::errors::stale_handle_error(
            "handle belongs to another native engine",
        ));
    }
    Ok(true)
}

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<EngineHandle>()?;
    m.add_function(wrap_pyfunction!(create, m)?)?;
    m.add_function(wrap_pyfunction!(close, m)?)?;
    m.add_function(wrap_pyfunction!(snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(assert_same_owner, m)?)?;
    m.add("HANDLE_KIND_ENGINE", HandleKind::Engine.as_str())?;
    Ok(())
}
