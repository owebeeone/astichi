use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::materialize_ir::NativeMaterializationWorkspace;
use crate::occurrence_store::{NativeAssemblyState, NativeTemplate};
use crate::surface_registry::RegisteredSurfaceBundle;

pub const HANDLE_KIND_ENGINE: &str = "engine";

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct EngineHandle {
    epoch: u64,
    owner_id: u64,
    index: u64,
    generation: u64,
    closed: bool,
    surface_bundle: Option<RegisteredSurfaceBundle>,
    templates: Vec<NativeTemplate>,
    states: Vec<NativeAssemblyState>,
    workspaces: Vec<NativeMaterializationWorkspace>,
}

impl EngineHandle {
    pub fn new(owner_id: u64) -> Self {
        Self {
            epoch: 1,
            owner_id,
            index: 0,
            generation: 0,
            closed: false,
            surface_bundle: None,
            templates: Vec::new(),
            states: Vec::new(),
            workspaces: Vec::new(),
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

    pub fn surface_bundle(&self) -> Option<&RegisteredSurfaceBundle> {
        self.surface_bundle.as_ref()
    }

    pub fn template_count(&self) -> usize {
        self.templates.len()
    }

    pub fn push_template(&mut self, template: NativeTemplate) -> PyResult<usize> {
        self.ensure_open()?;
        let index = self.templates.len();
        self.templates.push(template);
        Ok(index)
    }

    pub fn template(&self, index: usize) -> PyResult<&NativeTemplate> {
        self.ensure_open()?;
        self.templates
            .get(index)
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native template handle"))
    }

    pub fn templates(&self) -> &[NativeTemplate] {
        &self.templates
    }

    pub fn push_state(&mut self, state: NativeAssemblyState) -> PyResult<usize> {
        self.ensure_open()?;
        let index = self.states.len();
        self.states.push(state);
        Ok(index)
    }

    pub fn state(&self, index: usize) -> PyResult<&NativeAssemblyState> {
        self.ensure_open()?;
        self.states.get(index).ok_or_else(|| {
            crate::errors::stale_handle_error("unknown native assembly state handle")
        })
    }

    pub fn state_mut(&mut self, index: usize) -> PyResult<&mut NativeAssemblyState> {
        self.ensure_open()?;
        self.states.get_mut(index).ok_or_else(|| {
            crate::errors::stale_handle_error("unknown native assembly state handle")
        })
    }

    pub fn push_workspace(&mut self, workspace: NativeMaterializationWorkspace) -> PyResult<usize> {
        self.ensure_open()?;
        let index = self.workspaces.len();
        self.workspaces.push(workspace);
        Ok(index)
    }

    pub fn workspace(&self, index: usize) -> PyResult<&NativeMaterializationWorkspace> {
        self.ensure_open()?;
        self.workspaces.get(index).ok_or_else(|| {
            crate::errors::stale_handle_error("unknown native materialization workspace handle")
        })
    }

    pub fn workspace_mut(&mut self, index: usize) -> PyResult<&mut NativeMaterializationWorkspace> {
        self.ensure_open()?;
        self.workspaces.get_mut(index).ok_or_else(|| {
            crate::errors::stale_handle_error("unknown native materialization workspace handle")
        })
    }

    pub fn set_surface_bundle(&mut self, bundle: RegisteredSurfaceBundle) -> PyResult<()> {
        self.ensure_open()?;
        if self.surface_bundle.is_some() {
            return Err(crate::errors::schema_error(
                "surface bundle is already registered",
            ));
        }
        self.surface_bundle = Some(bundle);
        Ok(())
    }

    pub fn snapshot_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        dict.set_item("engine_epoch", self.epoch)?;
        dict.set_item("owner_id", self.owner_id)?;
        dict.set_item("kind", HANDLE_KIND_ENGINE)?;
        dict.set_item("index", self.index)?;
        dict.set_item("generation", self.generation)?;
        dict.set_item("closed", self.closed)?;
        dict.set_item("surface_bundle_registered", self.surface_bundle.is_some())?;
        if let Some(bundle) = self.surface_bundle.as_ref() {
            dict.set_item("surface_count", bundle.surface_count())?;
            dict.set_item("operation_count", bundle.operation_count())?;
            dict.set_item("pattern_count", bundle.pattern_count())?;
        } else {
            dict.set_item("surface_count", 0)?;
            dict.set_item("operation_count", 0)?;
            dict.set_item("pattern_count", 0)?;
        }
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
        HANDLE_KIND_ENGINE
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
