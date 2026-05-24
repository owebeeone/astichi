use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::PyErr;

pub fn stale_handle_error(message: &str) -> PyErr {
    PyRuntimeError::new_err(format!("native stale handle: {message}"))
}

pub fn schema_error(message: &str) -> PyErr {
    PyValueError::new_err(format!("native schema error: {message}"))
}
