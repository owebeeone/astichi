use pyo3::prelude::*;
use pyo3::types::PyDict;

#[derive(Clone, Copy)]
pub enum HandleKind {
    Engine,
}

impl HandleKind {
    pub fn as_str(self) -> &'static str {
        match self {
            HandleKind::Engine => "engine",
        }
    }
}

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct EngineHandle {
    epoch: u64,
    owner_id: u64,
    kind: HandleKind,
    index: u64,
    generation: u64,
    closed: bool,
}

impl EngineHandle {
    pub fn new(owner_id: u64) -> Self {
        Self {
            epoch: 1,
            owner_id,
            kind: HandleKind::Engine,
            index: 0,
            generation: 0,
            closed: false,
        }
    }

    pub fn owner_id(&self) -> u64 {
        self.owner_id
    }

    pub fn ensure_open(&self) -> PyResult<()> {
        if self.closed {
            return Err(crate::errors::stale_handle_error(
                "engine handle is already closed",
            ));
        }
        Ok(())
    }

    pub fn close(&mut self) {
        self.closed = true;
        self.generation += 1;
    }

    pub fn snapshot_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        dict.set_item("engine_epoch", self.epoch)?;
        dict.set_item("owner_id", self.owner_id)?;
        dict.set_item("kind", self.kind.as_str())?;
        dict.set_item("index", self.index)?;
        dict.set_item("generation", self.generation)?;
        dict.set_item("closed", self.closed)?;
        Ok(dict.into_any().unbind())
    }
}

#[pymethods]
impl EngineHandle {
    #[getter]
    fn engine_epoch(&self) -> u64 {
        self.epoch
    }

    #[getter]
    fn kind(&self) -> &'static str {
        self.kind.as_str()
    }

    #[getter]
    fn generation(&self) -> u64 {
        self.generation
    }

    #[getter]
    fn closed(&self) -> bool {
        self.closed
    }

    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.snapshot_dict(py)
    }
}
