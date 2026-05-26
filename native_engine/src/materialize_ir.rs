use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet};

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyModule};
use rustpython_parser::ast;

use crate::handles::EngineHandle;
use crate::occurrence_store::{
    NativeAssemblyStateHandle, NativeEdgeHandle, NativeOverlayHandle, NativeTemplateHandle,
    RecordKey,
};

const HANDLE_KIND_WORKSPACE: &str = "materialization-workspace";

#[derive(Clone)]
pub struct NativeMaterializationWorkspace {
    template_index: usize,
    module: ast::ModModule,
}

impl NativeMaterializationWorkspace {
    fn new(template_index: usize, module: ast::ModModule) -> Self {
        Self {
            template_index,
            module,
        }
    }

    fn module(&self) -> &ast::ModModule {
        &self.module
    }

    fn module_mut(&mut self) -> &mut ast::ModModule {
        &mut self.module
    }
}

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct NativeMaterializationWorkspaceHandle {
    owner_id: u64,
    index: usize,
    generation: u64,
}

impl NativeMaterializationWorkspaceHandle {
    fn new(owner_id: u64, index: usize) -> Self {
        Self {
            owner_id,
            index,
            generation: 0,
        }
    }
}

#[pymethods]
impl NativeMaterializationWorkspaceHandle {
    #[getter]
    fn kind(&self) -> &'static str {
        HANDLE_KIND_WORKSPACE
    }

    #[getter]
    fn generation(&self) -> u64 {
        self.generation
    }
}

#[pyfunction(name = "materialization_workspace_create")]
fn materialization_workspace_create(
    mut engine: PyRefMut<'_, EngineHandle>,
    template: PyRef<'_, NativeTemplateHandle>,
) -> PyResult<NativeMaterializationWorkspaceHandle> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), template.owner_id())?;
    let module = engine
        .template(template.template_index())?
        .module()
        .ok_or_else(|| {
            crate::errors::schema_error("native template does not carry native parser IR")
        })?
        .clone();
    let workspace = NativeMaterializationWorkspace::new(template.template_index(), module);
    let index = engine.push_workspace(workspace)?;
    Ok(NativeMaterializationWorkspaceHandle::new(
        engine.owner_id(),
        index,
    ))
}

#[pyfunction(name = "materialization_workspace_snapshot")]
fn materialization_workspace_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    let workspace_ref = engine.workspace(workspace.index)?;
    let template = engine.template(workspace_ref.template_index)?;
    let snapshot = PyDict::new(py);
    snapshot.set_item("body_len", workspace_ref.module().body.len())?;
    snapshot.set_item("body_kinds", body_kinds(&workspace_ref.module().body))?;
    snapshot.set_item("kind", HANDLE_KIND_WORKSPACE)?;
    snapshot.set_item("locator_count", template.locator_count())?;
    snapshot.set_item("template_id", workspace_ref.template_index)?;
    Ok(snapshot.into_any().unbind())
}

#[pyfunction(name = "materialization_workspace_resolve_locator")]
fn materialization_workspace_resolve_locator(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    locator_id: usize,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    let workspace_ref = engine.workspace(workspace.index)?;
    let template = engine.template(workspace_ref.template_index)?;
    let ast_path = template.locator_ast_path(locator_id)?;
    let resolved_kind = resolve_ast_path(workspace_ref.module(), ast_path)?;
    let snapshot = PyDict::new(py);
    snapshot.set_item("ast_path", ast_path)?;
    snapshot.set_item("locator_id", locator_id)?;
    snapshot.set_item("resolved_kind", resolved_kind)?;
    snapshot.set_item("template_id", workspace_ref.template_index)?;
    Ok(snapshot.into_any().unbind())
}

#[pyfunction(name = "materialization_workspace_resolve_ast_path")]
fn materialization_workspace_resolve_ast_path(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    ast_path: String,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    let workspace_ref = engine.workspace(workspace.index)?;
    let resolved_kind = resolve_ast_path(workspace_ref.module(), &ast_path)?;
    let snapshot = PyDict::new(py);
    snapshot.set_item("ast_path", ast_path)?;
    snapshot.set_item("resolved_kind", resolved_kind)?;
    snapshot.set_item("template_id", workspace_ref.template_index)?;
    Ok(snapshot.into_any().unbind())
}

#[pyfunction(name = "materialization_workspace_replace_statement_with_pass")]
fn materialization_workspace_replace_statement_with_pass(
    mut engine: PyRefMut<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    locator_id: usize,
) -> PyResult<()> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    let statement_path = {
        let workspace_ref = engine.workspace(workspace.index)?;
        let template = engine.template(workspace_ref.template_index)?;
        statement_path_for_locator(template.locator_ast_path(locator_id)?)?
    };
    let pass = pass_statement()?;
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    replace_statement_at_path(workspace_ref.module_mut(), &statement_path, pass)
}

#[pyfunction(name = "materialization_workspace_apply_expression_edge")]
fn materialization_workspace_apply_expression_edge(
    mut engine: PyRefMut<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    edge: PyRef<'_, NativeEdgeHandle>,
) -> PyResult<()> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    ensure_owner(engine.owner_id(), state.owner_id())?;
    ensure_owner(engine.owner_id(), edge.owner_id())?;
    if edge.edge_state_index() != state.state_index() {
        return Err(crate::errors::stale_handle_error(
            "edge belongs to another native assembly state",
        ));
    }
    let (target_path, replacement) = {
        let workspace_ref = engine.workspace(workspace.index)?;
        let state_ref = engine.state(state.state_index())?;
        let edge_ref = state_ref.edge(edge.edge_index())?;
        if edge_ref.operation_key() != "astichi.operation.replace_expression" {
            return Err(crate::errors::schema_error(&format!(
                "native expression materializer cannot apply `{}`",
                edge_ref.operation_key()
            )));
        }
        let target_key = edge_ref.target_record();
        let target_occurrence = state_ref.occurrence(target_key.occurrence_index())?;
        if target_occurrence.template_index() != workspace_ref.template_index {
            return Err(crate::errors::schema_error(
                "workspace template does not match expression edge target occurrence",
            ));
        }
        let target_template = engine.template(target_occurrence.template_index())?;
        let target_path = target_template
            .locator_ast_path_for_record(target_key.template_record_index())?
            .to_string();
        let source_occurrence = state_ref.occurrence(edge_ref.source_occurrence_index())?;
        let source_template = engine.template(source_occurrence.template_index())?;
        let source_module = source_template.module().ok_or_else(|| {
            crate::errors::schema_error("native source template does not carry native parser IR")
        })?;
        let source_path = source_template
            .unique_locator_ast_path_for_surface("astichi.surface.expression.production")?;
        let replacement = clone_expr_at_path(source_module, source_path)?;
        (target_path, replacement)
    };
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    replace_expr_at_path(workspace_ref.module_mut(), &target_path, replacement)
}

#[pyfunction(name = "materialization_workspace_apply_block_edge")]
fn materialization_workspace_apply_block_edge(
    mut engine: PyRefMut<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    edge: PyRef<'_, NativeEdgeHandle>,
) -> PyResult<()> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    ensure_owner(engine.owner_id(), state.owner_id())?;
    ensure_owner(engine.owner_id(), edge.owner_id())?;
    if edge.edge_state_index() != state.state_index() {
        return Err(crate::errors::stale_handle_error(
            "edge belongs to another native assembly state",
        ));
    }
    let (target_statement_path, replacement) = {
        let workspace_ref = engine.workspace(workspace.index)?;
        let state_ref = engine.state(state.state_index())?;
        let edge_ref = state_ref.edge(edge.edge_index())?;
        if edge_ref.operation_key() != "astichi.operation.splice_body_at_marker" {
            return Err(crate::errors::schema_error(&format!(
                "native block materializer cannot apply `{}`",
                edge_ref.operation_key()
            )));
        }
        let target_key = edge_ref.target_record();
        let target_occurrence = state_ref.occurrence(target_key.occurrence_index())?;
        if target_occurrence.template_index() != workspace_ref.template_index {
            return Err(crate::errors::schema_error(
                "workspace template does not match block edge target occurrence",
            ));
        }
        let target_template = engine.template(target_occurrence.template_index())?;
        let target_locator_path = target_template
            .locator_ast_path_for_record(target_key.template_record_index())?
            .to_string();
        let target_statement_path = statement_path_for_locator(&target_locator_path)?;
        let source_occurrence = state_ref.occurrence(edge_ref.source_occurrence_index())?;
        let source_template = engine.template(source_occurrence.template_index())?;
        let source_module = source_template.module().ok_or_else(|| {
            crate::errors::schema_error("native source template does not carry native parser IR")
        })?;
        (target_statement_path, source_module.body.clone())
    };
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    replace_statements_at_path(
        workspace_ref.module_mut(),
        &target_statement_path,
        replacement,
    )
}

#[pyfunction(name = "materialization_workspace_apply_parameter_edge")]
fn materialization_workspace_apply_parameter_edge(
    mut engine: PyRefMut<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    edge: PyRef<'_, NativeEdgeHandle>,
) -> PyResult<()> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    ensure_owner(engine.owner_id(), state.owner_id())?;
    ensure_owner(engine.owner_id(), edge.owner_id())?;
    if edge.edge_state_index() != state.state_index() {
        return Err(crate::errors::stale_handle_error(
            "edge belongs to another native assembly state",
        ));
    }
    let (target_path, target_name, payload_args) = {
        let workspace_ref = engine.workspace(workspace.index)?;
        let state_ref = engine.state(state.state_index())?;
        let edge_ref = state_ref.edge(edge.edge_index())?;
        if edge_ref.operation_key() != "astichi.operation.splice_parameters" {
            return Err(crate::errors::schema_error(&format!(
                "native parameter materializer cannot apply `{}`",
                edge_ref.operation_key()
            )));
        }
        let target_key = edge_ref.target_record();
        let target_occurrence = state_ref.occurrence(target_key.occurrence_index())?;
        if target_occurrence.template_index() != workspace_ref.template_index {
            return Err(crate::errors::schema_error(
                "workspace template does not match parameter edge target occurrence",
            ));
        }
        let target_template = engine.template(target_occurrence.template_index())?;
        let target_path = target_template
            .locator_ast_path_for_record(target_key.template_record_index())?
            .to_string();
        let target_name = target_template
            .records()
            .get(target_key.template_record_index())
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native template record"))?
            .resource_name()
            .to_string();
        let source_occurrence = state_ref.occurrence(edge_ref.source_occurrence_index())?;
        let source_template = engine.template(source_occurrence.template_index())?;
        let source_module = source_template.module().ok_or_else(|| {
            crate::errors::schema_error("native source template does not carry native parser IR")
        })?;
        let source_path = source_template
            .unique_locator_ast_path_for_surface("astichi.surface.parameter.production")?;
        let payload_args = clone_function_args_at_path(source_module, source_path)?;
        (target_path, target_name, payload_args)
    };
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    splice_parameters_at_path(
        workspace_ref.module_mut(),
        &target_path,
        &target_name,
        payload_args,
    )
}

#[pyfunction(name = "materialization_workspace_apply_call_argument_edge")]
fn materialization_workspace_apply_call_argument_edge(
    mut engine: PyRefMut<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    edge: PyRef<'_, NativeEdgeHandle>,
) -> PyResult<()> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    ensure_owner(engine.owner_id(), state.owner_id())?;
    ensure_owner(engine.owner_id(), edge.owner_id())?;
    if edge.edge_state_index() != state.state_index() {
        return Err(crate::errors::stale_handle_error(
            "edge belongs to another native assembly state",
        ));
    }
    let (target_path, payload_args, payload_keywords) = {
        let workspace_ref = engine.workspace(workspace.index)?;
        let state_ref = engine.state(state.state_index())?;
        let edge_ref = state_ref.edge(edge.edge_index())?;
        if edge_ref.operation_key() != "astichi.operation.splice_call_arguments" {
            return Err(crate::errors::schema_error(&format!(
                "native call-argument materializer cannot apply `{}`",
                edge_ref.operation_key()
            )));
        }
        let target_key = edge_ref.target_record();
        let target_occurrence = state_ref.occurrence(target_key.occurrence_index())?;
        if target_occurrence.template_index() != workspace_ref.template_index {
            return Err(crate::errors::schema_error(
                "workspace template does not match call-argument edge target occurrence",
            ));
        }
        let target_template = engine.template(target_occurrence.template_index())?;
        let target_path = target_template
            .locator_ast_path_for_record(target_key.template_record_index())?
            .to_string();
        let source_occurrence = state_ref.occurrence(edge_ref.source_occurrence_index())?;
        let source_template = engine.template(source_occurrence.template_index())?;
        let source_module = source_template.module().ok_or_else(|| {
            crate::errors::schema_error("native source template does not carry native parser IR")
        })?;
        let source_path = source_template
            .unique_locator_ast_path_for_surface("astichi.surface.funcargs.production")?;
        let (payload_args, payload_keywords) =
            clone_funcargs_payload_at_path(source_module, source_path)?;
        (target_path, payload_args, payload_keywords)
    };
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    splice_call_arguments_at_path(
        workspace_ref.module_mut(),
        &target_path,
        payload_args,
        payload_keywords,
    )
}

#[pyfunction(name = "materialization_workspace_lower_literal_refs")]
fn materialization_workspace_lower_literal_refs(
    mut engine: PyRefMut<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
) -> PyResult<usize> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    lower_literal_refs_in_module(workspace_ref.module_mut())
}

#[pyfunction(name = "materialization_workspace_apply_external_overlay_literal")]
fn materialization_workspace_apply_external_overlay_literal(
    mut engine: PyRefMut<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    overlay: PyRef<'_, NativeOverlayHandle>,
    expression_source: String,
) -> PyResult<usize> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    ensure_owner(engine.owner_id(), state.owner_id())?;
    ensure_owner(engine.owner_id(), overlay.owner_id())?;
    if overlay.overlay_state_index() != state.state_index() {
        return Err(crate::errors::stale_handle_error(
            "overlay belongs to another native assembly state",
        ));
    }
    let external_name = {
        let state_ref = engine.state(state.state_index())?;
        let overlay_ref = state_ref.overlay(overlay.overlay_index())?;
        if overlay_ref.kind() != "external" {
            return Err(crate::errors::schema_error(&format!(
                "native external materializer cannot apply `{}` overlay",
                overlay_ref.kind()
            )));
        }
        overlay_ref.source_label().to_string()
    };
    let replacement = parse_expression_module(&expression_source, "<astichi-external>")?;
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    substitute_external_literal_in_module(workspace_ref.module_mut(), &external_name, &replacement)
}

#[pyfunction(name = "materialization_workspace_apply_identifier_overlay")]
fn materialization_workspace_apply_identifier_overlay(
    mut engine: PyRefMut<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    overlay: PyRef<'_, NativeOverlayHandle>,
) -> PyResult<usize> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    ensure_owner(engine.owner_id(), state.owner_id())?;
    ensure_owner(engine.owner_id(), overlay.owner_id())?;
    if overlay.overlay_state_index() != state.state_index() {
        return Err(crate::errors::stale_handle_error(
            "overlay belongs to another native assembly state",
        ));
    }
    let (authored_name, resolved_name) = {
        let workspace_ref = engine.workspace(workspace.index)?;
        let state_ref = engine.state(state.state_index())?;
        let overlay_ref = state_ref.overlay(overlay.overlay_index())?;
        if !matches!(overlay_ref.kind(), "identifier" | "identifier_suffix") {
            return Err(crate::errors::schema_error(&format!(
                "native identifier materializer cannot apply `{}` overlay",
                overlay_ref.kind()
            )));
        }
        let target_key = overlay_ref.target_record();
        let target_occurrence = state_ref.occurrence(target_key.occurrence_index())?;
        if target_occurrence.template_index() != workspace_ref.template_index {
            return Err(crate::errors::schema_error(
                "workspace template does not match identifier overlay target occurrence",
            ));
        }
        let target_template = engine.template(target_occurrence.template_index())?;
        let record = target_template
            .records()
            .get(target_key.template_record_index())
            .ok_or_else(|| {
                crate::errors::stale_handle_error("unknown native template record handle")
            })?;
        let authored_name = if overlay_ref.kind() == "identifier_suffix" {
            format!("{}__astichi_arg__", record.resource_name())
        } else {
            record.resource_name().to_string()
        };
        (authored_name, overlay_ref.source_label().to_string())
    };
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    rewrite_identifier_in_module(workspace_ref.module_mut(), &authored_name, &resolved_name)
}

#[pyfunction(name = "assembly_state_materialize_to_python_ast")]
#[pyo3(signature = (engine, state, external_literals, root_occurrence_index = None, location_policy = "fix_missing"))]
fn assembly_state_materialize_to_python_ast(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    external_literals: &Bound<'_, PyDict>,
    root_occurrence_index: Option<usize>,
    location_policy: &str,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id())?;
    let state_ref = engine.state(state.state_index())?;
    let root = match root_occurrence_index {
        Some(index) => {
            state_ref.occurrence(index)?;
            index
        }
        None => default_root_occurrence_index(state_ref)?,
    };
    let external_literals = parse_external_literals(external_literals)?;
    let mut cache = BTreeMap::new();
    let mut visiting = BTreeSet::new();
    let module = materialize_occurrence_module(
        &engine,
        state_ref,
        root,
        &external_literals,
        &mut cache,
        &mut visiting,
    )?;
    crate::parser_ir::convert_module_artifact(py, "", &module, location_policy)
        .map(|(artifact, _stats)| artifact)
}

#[pyfunction(name = "materialization_workspace_copy_to_python_ast")]
#[pyo3(signature = (engine, workspace, location_policy = "fix_missing"))]
fn materialization_workspace_copy_to_python_ast(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    location_policy: &str,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), workspace.owner_id)?;
    let workspace_ref = engine.workspace(workspace.index)?;
    crate::parser_ir::convert_module_artifact(py, "", workspace_ref.module(), location_policy)
        .map(|(artifact, _stats)| artifact)
}

#[pyfunction(name = "materialization_workspace_to_source")]
#[pyo3(signature = (engine, workspace, location_policy = "fix_missing"))]
fn materialization_workspace_to_source(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    workspace: PyRef<'_, NativeMaterializationWorkspaceHandle>,
    location_policy: &str,
) -> PyResult<String> {
    let module =
        materialization_workspace_copy_to_python_ast(py, engine, workspace, location_policy)?;
    let ast_mod = py.import("ast")?;
    ast_mod.getattr("unparse")?.call1((module,))?.extract()
}

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeMaterializationWorkspaceHandle>()?;
    m.add_function(wrap_pyfunction!(materialization_workspace_create, m)?)?;
    m.add_function(wrap_pyfunction!(materialization_workspace_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_resolve_locator,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_resolve_ast_path,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_replace_statement_with_pass,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_apply_expression_edge,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_apply_block_edge,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_apply_parameter_edge,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_apply_call_argument_edge,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_lower_literal_refs,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_apply_external_overlay_literal,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_apply_identifier_overlay,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        assembly_state_materialize_to_python_ast,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_copy_to_python_ast,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(materialization_workspace_to_source, m)?)?;
    m.add(
        "HANDLE_KIND_MATERIALIZATION_WORKSPACE",
        HANDLE_KIND_WORKSPACE,
    )?;
    Ok(())
}

fn ensure_owner(expected: u64, actual: u64) -> PyResult<()> {
    if expected != actual {
        return Err(crate::errors::stale_handle_error(
            "handle belongs to another native engine",
        ));
    }
    Ok(())
}

fn parse_external_literals(dict: &Bound<'_, PyDict>) -> PyResult<BTreeMap<usize, String>> {
    let mut values = BTreeMap::new();
    for (key, value) in dict.iter() {
        let overlay_index = key
            .extract::<usize>()
            .map_err(|_| crate::errors::schema_error("external literal keys must be integers"))?;
        let expression_source = value.extract::<String>().map_err(|_| {
            crate::errors::schema_error("external literal values must be expression source strings")
        })?;
        values.insert(overlay_index, expression_source);
    }
    Ok(values)
}

fn default_root_occurrence_index(
    state: &crate::occurrence_store::NativeAssemblyState,
) -> PyResult<usize> {
    state
        .occurrences()
        .iter()
        .enumerate()
        .find_map(|(index, occurrence)| {
            if occurrence.parent_occurrence_index().is_none() && occurrence.live() {
                Some(index)
            } else {
                None
            }
        })
        .ok_or_else(|| crate::errors::schema_error("native assembly state has no root occurrence"))
}

fn materialize_occurrence_module(
    engine: &EngineHandle,
    state: &crate::occurrence_store::NativeAssemblyState,
    occurrence_index: usize,
    external_literals: &BTreeMap<usize, String>,
    cache: &mut BTreeMap<usize, ast::ModModule>,
    visiting: &mut BTreeSet<usize>,
) -> PyResult<ast::ModModule> {
    if let Some(module) = cache.get(&occurrence_index) {
        return Ok(module.clone());
    }
    if !visiting.insert(occurrence_index) {
        return Err(crate::errors::schema_error(
            "cycle detected while materializing native occurrence graph",
        ));
    }
    let occurrence = state.occurrence(occurrence_index)?;
    if !occurrence.live() {
        return Err(crate::errors::schema_error(
            "cannot materialize a dead native occurrence",
        ));
    }
    let template = engine.template(occurrence.template_index())?;
    let mut module = template
        .module()
        .ok_or_else(|| {
            crate::errors::schema_error("native template does not carry native parser IR")
        })?
        .clone();

    let mut edges = state
        .edges()
        .iter()
        .enumerate()
        .filter(|(_, edge)| edge.target_record().occurrence_index() == occurrence_index)
        .collect::<Vec<_>>();
    edges.sort_by_key(|(edge_index, edge)| (edge.order(), *edge_index));
    let mut materialized_edges = Vec::new();
    for (edge_index, edge) in edges {
        let source = materialize_occurrence_module(
            engine,
            state,
            edge.source_occurrence_index(),
            external_literals,
            cache,
            visiting,
        )?;
        materialized_edges.push(MaterializedEdgeInput {
            edge_index,
            source_module: source,
        });
    }
    apply_materialized_edges(engine, state, &mut module, &materialized_edges)?;

    for (overlay_index, overlay) in state.overlays().iter().enumerate() {
        if overlay.target_record().occurrence_index() != occurrence_index {
            continue;
        }
        apply_materialized_overlay(engine, state, &mut module, overlay_index, external_literals)?;
    }
    lower_native_statement_markers_in_module(&mut module)?;
    lower_literal_refs_in_module(&mut module)?;

    visiting.remove(&occurrence_index);
    cache.insert(occurrence_index, module.clone());
    Ok(module)
}

struct MaterializedEdgeInput {
    edge_index: usize,
    source_module: ast::ModModule,
}

fn apply_materialized_edges(
    engine: &EngineHandle,
    state: &crate::occurrence_store::NativeAssemblyState,
    module: &mut ast::ModModule,
    edges: &[MaterializedEdgeInput],
) -> PyResult<()> {
    let mut grouped: BTreeMap<(RecordKey, String), Vec<&MaterializedEdgeInput>> = BTreeMap::new();
    for edge_input in edges {
        let edge = state.edge(edge_input.edge_index)?;
        grouped
            .entry((edge.target_record(), edge.operation_key().to_string()))
            .or_default()
            .push(edge_input);
    }
    let mut ordered = Vec::new();
    for ((target_record, operation_key), group) in grouped {
        let statement_key =
            edge_group_statement_sort_key(engine, state, target_record, &operation_key)?;
        ordered.push((statement_key, target_record, operation_key, group));
    }
    ordered.sort_by(compare_edge_groups);
    for (_statement_key, target_record, operation_key, group) in ordered {
        apply_materialized_edge_group(
            engine,
            state,
            module,
            target_record,
            &operation_key,
            &group,
        )?;
    }
    Ok(())
}

fn edge_group_statement_sort_key(
    engine: &EngineHandle,
    state: &crate::occurrence_store::NativeAssemblyState,
    target_record: RecordKey,
    operation_key: &str,
) -> PyResult<Option<(usize, Vec<(String, usize)>)>> {
    let target_template = template_for_record(engine, state, target_record)?;
    let target_path = target_template
        .locator_ast_path_for_record(target_record.template_record_index())?
        .to_string();
    let statement_path = match operation_key {
        "astichi.operation.splice_body_at_marker" => statement_path_for_locator(&target_path)?,
        "astichi.operation.append_clause" => if_statement_path_for_elif_locator(&target_path)?,
        _ => return Ok(None),
    };
    Ok(Some(ast_path_order_key(&statement_path)?))
}

fn compare_edge_groups<'a>(
    left: &(
        Option<(usize, Vec<(String, usize)>)>,
        RecordKey,
        String,
        Vec<&'a MaterializedEdgeInput>,
    ),
    right: &(
        Option<(usize, Vec<(String, usize)>)>,
        RecordKey,
        String,
        Vec<&'a MaterializedEdgeInput>,
    ),
) -> Ordering {
    match (&left.0, &right.0) {
        (Some(left_key), Some(right_key)) => right_key.cmp(left_key),
        (Some(_), None) => Ordering::Less,
        (None, Some(_)) => Ordering::Greater,
        (None, None) => (left.1, &left.2).cmp(&(right.1, &right.2)),
    }
}

fn ast_path_order_key(path: &str) -> PyResult<(usize, Vec<(String, usize)>)> {
    let segments = parse_ast_path(path)?;
    Ok((
        segments.len(),
        segments
            .into_iter()
            .map(|segment| (segment.field, segment.index.unwrap_or(usize::MAX)))
            .collect(),
    ))
}

fn apply_materialized_edge_group(
    engine: &EngineHandle,
    state: &crate::occurrence_store::NativeAssemblyState,
    module: &mut ast::ModModule,
    target_record: RecordKey,
    operation_key: &str,
    edges: &[&MaterializedEdgeInput],
) -> PyResult<()> {
    let target_template = template_for_record(engine, state, target_record)?;
    let target_path = target_template
        .locator_ast_path_for_record(target_record.template_record_index())?
        .to_string();
    match operation_key {
        "astichi.operation.replace_expression" => {
            let edge = only_edge(edges, operation_key)?;
            let native_edge = state.edge(edge.edge_index)?;
            let source_occurrence = state.occurrence(native_edge.source_occurrence_index())?;
            let source_template = engine.template(source_occurrence.template_index())?;
            let source_path = source_template
                .unique_locator_ast_path_for_surface("astichi.surface.expression.production")?;
            let replacement = clone_expr_at_path(&edge.source_module, source_path)?;
            replace_expr_at_path(module, &target_path, replacement)
        }
        "astichi.operation.splice_body_at_marker" => {
            let target_statement_path = statement_path_for_locator(&target_path)?;
            let mut statements = Vec::new();
            for edge in edges {
                statements.extend(edge.source_module.body.clone());
            }
            replace_statements_at_path(module, &target_statement_path, statements)
        }
        "astichi.operation.splice_parameters" => {
            let mut payload_args = empty_arguments();
            for edge in edges {
                let native_edge = state.edge(edge.edge_index)?;
                let source_occurrence = state.occurrence(native_edge.source_occurrence_index())?;
                let source_template = engine.template(source_occurrence.template_index())?;
                let source_path = source_template
                    .unique_locator_ast_path_for_surface("astichi.surface.parameter.production")?;
                append_argument_payload(
                    &mut payload_args,
                    clone_function_args_at_path(&edge.source_module, source_path)?,
                )?;
            }
            let target_name = target_template
                .records()
                .get(target_record.template_record_index())
                .ok_or_else(|| crate::errors::stale_handle_error("unknown native template record"))?
                .resource_name()
                .to_string();
            splice_parameters_at_path(module, &target_path, &target_name, payload_args)
        }
        "astichi.operation.splice_call_arguments" => {
            let mut payload_args = Vec::new();
            let mut payload_keywords = Vec::new();
            for edge in edges {
                let native_edge = state.edge(edge.edge_index)?;
                let source_occurrence = state.occurrence(native_edge.source_occurrence_index())?;
                let source_template = engine.template(source_occurrence.template_index())?;
                let (mut args, mut keywords) = materialized_call_argument_payload(
                    source_template,
                    &edge.source_module,
                    &target_path,
                )?;
                payload_args.append(&mut args);
                payload_keywords.append(&mut keywords);
            }
            splice_call_arguments_at_path(module, &target_path, payload_args, payload_keywords)
        }
        "astichi.operation.append_clause" => {
            let marker_if_path = if_statement_path_for_elif_locator(&target_path)?;
            let marker_if = clone_if_at_path(module, &marker_if_path)?;
            let mut chain = marker_if.orelse.clone();
            for edge in edges.iter().rev() {
                let native_edge = state.edge(edge.edge_index)?;
                let source_occurrence = state.occurrence(native_edge.source_occurrence_index())?;
                let source_template = engine.template(source_occurrence.template_index())?;
                let source_path = source_template
                    .unique_locator_ast_path_for_surface("astichi.surface.elif.production")?;
                let payload_if = clone_elif_payload_if_at_path(&edge.source_module, source_path)?;
                chain = vec![ast::Stmt::If(ast::StmtIf {
                    range: marker_if.range,
                    test: payload_if.test.clone(),
                    body: payload_if.body.clone(),
                    orelse: chain,
                })];
            }
            replace_statements_at_path(module, &marker_if_path, chain)
        }
        other => Err(crate::errors::schema_error(&format!(
            "native recursive materializer cannot apply `{other}`"
        ))),
    }
}

fn only_edge<'a>(
    edges: &'a [&MaterializedEdgeInput],
    operation_key: &str,
) -> PyResult<&'a MaterializedEdgeInput> {
    if edges.len() == 1 {
        Ok(edges[0])
    } else {
        Err(crate::errors::schema_error(&format!(
            "native recursive materializer expected one `{operation_key}` edge"
        )))
    }
}

fn empty_arguments() -> ast::Arguments {
    ast::Arguments {
        range: Default::default(),
        posonlyargs: Vec::new(),
        args: Vec::new(),
        vararg: None,
        kwonlyargs: Vec::new(),
        kwarg: None,
    }
}

fn append_argument_payload(
    target: &mut ast::Arguments,
    mut payload: ast::Arguments,
) -> PyResult<()> {
    if let Some(vararg) = payload.vararg.take() {
        if target.vararg.is_some() {
            return Err(crate::errors::schema_error(
                "native recursive parameter materializer would create multiple varargs",
            ));
        }
        target.vararg = Some(vararg);
    }
    if let Some(kwarg) = payload.kwarg.take() {
        if target.kwarg.is_some() {
            return Err(crate::errors::schema_error(
                "native recursive parameter materializer would create multiple kwargs",
            ));
        }
        target.kwarg = Some(kwarg);
    }
    target.posonlyargs.append(&mut payload.posonlyargs);
    target.args.append(&mut payload.args);
    target.kwonlyargs.append(&mut payload.kwonlyargs);
    Ok(())
}

fn materialized_call_argument_payload(
    source_template: &crate::occurrence_store::NativeTemplate,
    source_module: &ast::ModModule,
    target_path: &str,
) -> PyResult<(Vec<ast::Expr>, Vec<ast::Keyword>)> {
    if let Ok(source_path) =
        source_template.unique_locator_ast_path_for_surface("astichi.surface.funcargs.production")
    {
        return clone_funcargs_payload_at_path(source_module, source_path);
    }
    let source_path = source_template
        .unique_locator_ast_path_for_surface("astichi.surface.expression.production")?;
    let expression = clone_expr_at_path(source_module, source_path)?;
    if target_path.contains("/keywords[") {
        return expression_to_keyword_payload(expression);
    }
    Ok((vec![expression], Vec::new()))
}

fn expression_to_keyword_payload(
    expression: ast::Expr,
) -> PyResult<(Vec<ast::Expr>, Vec<ast::Keyword>)> {
    match expression {
        ast::Expr::Dict(node) => {
            let mut keywords = Vec::new();
            for (key, value) in node.keys.into_iter().zip(node.values.into_iter()) {
                let Some(key) = key else {
                    return Err(crate::errors::schema_error(
                        "native named-variadic expression payload cannot contain ** unpacking",
                    ));
                };
                let ast::Expr::Constant(constant) = key else {
                    return Err(crate::errors::schema_error(
                        "native named-variadic expression payload keys must be string constants",
                    ));
                };
                let ast::Constant::Str(name) = constant.value else {
                    return Err(crate::errors::schema_error(
                        "native named-variadic expression payload keys must be strings",
                    ));
                };
                keywords.push(ast::Keyword {
                    range: Default::default(),
                    arg: Some(ast::Identifier::new(name)),
                    value,
                });
            }
            Ok((Vec::new(), keywords))
        }
        _ => Err(crate::errors::schema_error(
            "native named-variadic expression payload must be a dict literal",
        )),
    }
}

fn apply_materialized_overlay(
    engine: &EngineHandle,
    state: &crate::occurrence_store::NativeAssemblyState,
    module: &mut ast::ModModule,
    overlay_index: usize,
    external_literals: &BTreeMap<usize, String>,
) -> PyResult<()> {
    let overlay = state.overlay(overlay_index)?;
    match overlay.kind() {
        "external" => {
            let expression_source = external_literals.get(&overlay_index).ok_or_else(|| {
                crate::errors::schema_error("native materializer is missing external literal")
            })?;
            let replacement = parse_expression_module(expression_source, "<astichi-external>")?;
            substitute_external_literal_in_module(module, overlay.source_label(), &replacement)?;
            Ok(())
        }
        "identifier" | "identifier_suffix" => {
            let record = template_record_for_record(engine, state, overlay.target_record())?;
            let authored_name = if overlay.kind() == "identifier_suffix" {
                format!("{}__astichi_arg__", record.resource_name())
            } else {
                record.resource_name().to_string()
            };
            rewrite_identifier_in_module(module, &authored_name, overlay.source_label())?;
            Ok(())
        }
        other => Err(crate::errors::schema_error(&format!(
            "native recursive materializer cannot apply `{other}` overlay"
        ))),
    }
}

fn template_for_record<'a>(
    engine: &'a EngineHandle,
    state: &crate::occurrence_store::NativeAssemblyState,
    record: RecordKey,
) -> PyResult<&'a crate::occurrence_store::NativeTemplate> {
    let occurrence = state.occurrence(record.occurrence_index())?;
    engine.template(occurrence.template_index())
}

fn template_record_for_record<'a>(
    engine: &'a EngineHandle,
    state: &crate::occurrence_store::NativeAssemblyState,
    record: RecordKey,
) -> PyResult<&'a crate::occurrence_store::NativeTemplateRecord> {
    let template = template_for_record(engine, state, record)?;
    template
        .records()
        .get(record.template_record_index())
        .ok_or_else(|| crate::errors::stale_handle_error("unknown native template record"))
}

fn body_kinds(body: &[ast::Stmt]) -> Vec<&'static str> {
    body.iter().map(stmt_kind).collect()
}

fn pass_statement() -> PyResult<ast::Stmt> {
    let module = crate::parser_ir::parse_native_module("pass\n", "<astichi-pass>")?;
    module
        .body
        .into_iter()
        .next()
        .ok_or_else(|| crate::errors::schema_error("failed to construct pass statement"))
}

fn statement_path_for_locator(path: &str) -> PyResult<String> {
    if path.ends_with("/value") {
        let Some((statement_path, _)) = path.rsplit_once('/') else {
            return Err(crate::errors::schema_error(
                "marker locator does not include a statement path",
            ));
        };
        return Ok(statement_path.to_string());
    }
    Ok(path.to_string())
}

fn if_statement_path_for_elif_locator(path: &str) -> PyResult<String> {
    let Some((statement_path, field_name)) = path.rsplit_once('/') else {
        return Err(crate::errors::schema_error(
            "elif locator does not include a statement path",
        ));
    };
    if field_name != "test" {
        return Err(crate::errors::schema_error(
            "elif locator must point at an if-test expression",
        ));
    }
    Ok(statement_path.to_string())
}

fn clone_if_at_path(module: &ast::ModModule, path: &str) -> PyResult<ast::StmtIf> {
    match clone_stmt_at_path(module, path)? {
        ast::Stmt::If(node) => Ok(node),
        other => Err(crate::errors::schema_error(&format!(
            "native elif target expected If, got {}",
            stmt_kind(&other)
        ))),
    }
}

fn clone_elif_payload_if_at_path(module: &ast::ModModule, path: &str) -> PyResult<ast::StmtIf> {
    let stmt = clone_stmt_at_path(module, path)?;
    let ast::Stmt::FunctionDef(function) = stmt else {
        return Err(crate::errors::schema_error(
            "native elif production expected astichi_elif function",
        ));
    };
    if function.name.as_str() != "astichi_elif" {
        return Err(crate::errors::schema_error(
            "native elif production function must be named astichi_elif",
        ));
    }
    let payloads = function
        .body
        .into_iter()
        .filter(|stmt| !is_marker_only_statement(stmt))
        .collect::<Vec<_>>();
    if payloads.len() != 1 {
        return Err(crate::errors::schema_error(
            "native elif production must contain exactly one branch",
        ));
    }
    match payloads.into_iter().next().expect("length checked above") {
        ast::Stmt::If(node) if node.orelse.is_empty() => Ok(node),
        _ => Err(crate::errors::schema_error(
            "native elif production branch must be an if without else",
        )),
    }
}

fn is_marker_only_statement(stmt: &ast::Stmt) -> bool {
    let ast::Stmt::Expr(node) = stmt else {
        return false;
    };
    let ast::Expr::Call(call) = node.value.as_ref() else {
        return false;
    };
    matches!(
        astichi_call_name(&call.func),
        Some("astichi_keep" | "astichi_import" | "astichi_pass" | "astichi_export")
    )
}

fn clone_stmt_at_path(module: &ast::ModModule, path: &str) -> PyResult<ast::Stmt> {
    let segments = parse_ast_path(path)?;
    clone_stmt_from_stmt_list(&module.body, &segments)
}

fn clone_stmt_from_stmt_list(body: &[ast::Stmt], segments: &[PathSegment]) -> PyResult<ast::Stmt> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "statement path cannot be the module root",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native statement path expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body statement segment requires an index"))?;
    let stmt = body.get(index).ok_or_else(|| {
        crate::errors::schema_error("native statement body index is out of range")
    })?;
    if rest.is_empty() {
        return Ok(stmt.clone());
    }
    clone_stmt_from_stmt(stmt, rest)
}

fn clone_stmt_from_stmt(stmt: &ast::Stmt, segments: &[PathSegment]) -> PyResult<ast::Stmt> {
    let Some((first, rest)) = segments.split_first() else {
        return Ok(stmt.clone());
    };
    match stmt {
        ast::Stmt::FunctionDef(node) if first.field == "body" => {
            clone_stmt_from_nested_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::AsyncFunctionDef(node) if first.field == "body" => {
            clone_stmt_from_nested_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::ClassDef(node) if first.field == "body" => {
            clone_stmt_from_nested_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::If(node) if first.field == "body" => {
            clone_stmt_from_nested_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::If(node) if first.field == "orelse" => {
            clone_stmt_from_nested_stmt_list(&node.orelse, first, rest)
        }
        ast::Stmt::For(node) if first.field == "body" => {
            clone_stmt_from_nested_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::For(node) if first.field == "orelse" => {
            clone_stmt_from_nested_stmt_list(&node.orelse, first, rest)
        }
        ast::Stmt::AsyncFor(node) if first.field == "body" => {
            clone_stmt_from_nested_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::AsyncFor(node) if first.field == "orelse" => {
            clone_stmt_from_nested_stmt_list(&node.orelse, first, rest)
        }
        ast::Stmt::While(node) if first.field == "body" => {
            clone_stmt_from_nested_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::While(node) if first.field == "orelse" => {
            clone_stmt_from_nested_stmt_list(&node.orelse, first, rest)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native statement path cannot enter field `{}` on {}",
            first.field,
            stmt_kind(stmt)
        ))),
    }
}

fn clone_stmt_from_nested_stmt_list(
    body: &[ast::Stmt],
    segment: &PathSegment,
    rest: &[PathSegment],
) -> PyResult<ast::Stmt> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!(
            "{} statement segment requires an index",
            segment.field
        ))
    })?;
    let stmt = body.get(index).ok_or_else(|| {
        crate::errors::schema_error("native statement body index is out of range")
    })?;
    if rest.is_empty() {
        return Ok(stmt.clone());
    }
    clone_stmt_from_stmt(stmt, rest)
}

#[derive(Clone)]
struct PathSegment {
    field: String,
    index: Option<usize>,
}

fn parse_ast_path(path: &str) -> PyResult<Vec<PathSegment>> {
    if path.is_empty() || path == "." {
        return Ok(Vec::new());
    }
    path.split('/').map(parse_path_segment).collect()
}

fn parse_path_segment(segment: &str) -> PyResult<PathSegment> {
    let Some((field, rest)) = segment.split_once('[') else {
        return Ok(PathSegment {
            field: segment.to_string(),
            index: None,
        });
    };
    let Some(index_text) = rest.strip_suffix(']') else {
        return Err(crate::errors::schema_error(&format!(
            "invalid native AST path segment `{segment}`"
        )));
    };
    let index = index_text.parse::<usize>().map_err(|_| {
        crate::errors::schema_error(&format!("invalid native AST path index `{segment}`"))
    })?;
    Ok(PathSegment {
        field: field.to_string(),
        index: Some(index),
    })
}

fn resolve_ast_path(module: &ast::ModModule, path: &str) -> PyResult<&'static str> {
    let segments = parse_ast_path(path)?;
    if segments.is_empty() {
        return Ok("Module");
    }
    resolve_from_stmt_list(&module.body, &segments)
}

fn resolve_from_stmt_list(body: &[ast::Stmt], segments: &[PathSegment]) -> PyResult<&'static str> {
    let Some((first, rest)) = segments.split_first() else {
        return Ok("StmtList");
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native locator expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body locator segment requires an index"))?;
    let stmt = body
        .get(index)
        .ok_or_else(|| crate::errors::schema_error("native locator body index is out of range"))?;
    if rest.is_empty() {
        return Ok(stmt_kind(stmt));
    }
    resolve_from_stmt(stmt, rest)
}

fn resolve_from_stmt(stmt: &ast::Stmt, segments: &[PathSegment]) -> PyResult<&'static str> {
    let Some((first, rest)) = segments.split_first() else {
        return Ok(stmt_kind(stmt));
    };
    match stmt {
        ast::Stmt::Expr(node) if first.field == "value" => resolve_from_expr(&node.value, rest),
        ast::Stmt::Assign(node) if first.field == "value" => resolve_from_expr(&node.value, rest),
        ast::Stmt::Assign(node) if first.field == "targets" => {
            let target = indexed_expr(&node.targets, first)?;
            resolve_from_expr(target, rest)
        }
        ast::Stmt::Delete(node) if first.field == "targets" => {
            let target = indexed_expr(&node.targets, first)?;
            resolve_from_expr(target, rest)
        }
        ast::Stmt::Return(node) if first.field == "value" => {
            let value = node
                .value
                .as_ref()
                .ok_or_else(|| crate::errors::schema_error("return locator value is missing"))?;
            resolve_from_expr(value, rest)
        }
        ast::Stmt::FunctionDef(node) if first.field == "body" => {
            resolve_indexed_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::AsyncFunctionDef(node) if first.field == "body" => {
            resolve_indexed_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::ClassDef(node) if first.field == "body" => {
            resolve_indexed_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::If(node) if first.field == "body" => {
            resolve_indexed_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::If(node) if first.field == "orelse" => {
            resolve_indexed_stmt_list(&node.orelse, first, rest)
        }
        ast::Stmt::For(node) if first.field == "body" => {
            resolve_indexed_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::For(node) if first.field == "orelse" => {
            resolve_indexed_stmt_list(&node.orelse, first, rest)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native locator cannot resolve statement field `{}` on {}",
            first.field,
            stmt_kind(stmt)
        ))),
    }
}

fn resolve_indexed_stmt_list(
    body: &[ast::Stmt],
    segment: &PathSegment,
    rest: &[PathSegment],
) -> PyResult<&'static str> {
    let Some(index) = segment.index else {
        return Ok("StmtList");
    };
    let stmt = body
        .get(index)
        .ok_or_else(|| crate::errors::schema_error("native locator body index is out of range"))?;
    if rest.is_empty() {
        return Ok(stmt_kind(stmt));
    }
    resolve_from_stmt(stmt, rest)
}

fn resolve_from_expr(expr: &ast::Expr, segments: &[PathSegment]) -> PyResult<&'static str> {
    let Some((first, rest)) = segments.split_first() else {
        return Ok(expr_kind(expr));
    };
    match expr {
        ast::Expr::Call(node) if first.field == "func" => resolve_from_expr(&node.func, rest),
        ast::Expr::Call(node) if first.field == "args" => {
            let arg = indexed_expr(&node.args, first)?;
            resolve_from_expr(arg, rest)
        }
        ast::Expr::Attribute(node) if first.field == "value" => {
            resolve_from_expr(&node.value, rest)
        }
        ast::Expr::BinOp(node) if first.field == "left" => resolve_from_expr(&node.left, rest),
        ast::Expr::BinOp(node) if first.field == "right" => resolve_from_expr(&node.right, rest),
        ast::Expr::Tuple(node) if first.field == "elts" => {
            let item = indexed_expr(&node.elts, first)?;
            resolve_from_expr(item, rest)
        }
        ast::Expr::List(node) if first.field == "elts" => {
            let item = indexed_expr(&node.elts, first)?;
            resolve_from_expr(item, rest)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native locator cannot resolve expression field `{}` on {}",
            first.field,
            expr_kind(expr)
        ))),
    }
}

fn indexed_expr<'a>(items: &'a [ast::Expr], segment: &PathSegment) -> PyResult<&'a ast::Expr> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!(
            "{} locator segment requires an index",
            segment.field
        ))
    })?;
    items.get(index).ok_or_else(|| {
        crate::errors::schema_error("native locator expression index is out of range")
    })
}

fn clone_expr_at_path(module: &ast::ModModule, path: &str) -> PyResult<ast::Expr> {
    let segments = parse_ast_path(path)?;
    clone_expr_from_stmt_list(&module.body, &segments)
}

fn clone_expr_from_stmt_list(body: &[ast::Stmt], segments: &[PathSegment]) -> PyResult<ast::Expr> {
    let Some((first, rest)) = segments.split_first() else {
        if body.len() == 1 {
            if let ast::Stmt::Expr(node) = &body[0] {
                return Ok((*node.value).clone());
            }
        }
        return Err(crate::errors::schema_error(
            "expression path must resolve to an expression node",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native expression path expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body expression segment requires an index"))?;
    let stmt = body.get(index).ok_or_else(|| {
        crate::errors::schema_error("native expression body index is out of range")
    })?;
    clone_expr_from_stmt(stmt, rest)
}

fn clone_expr_from_stmt(stmt: &ast::Stmt, segments: &[PathSegment]) -> PyResult<ast::Expr> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "expression path must include a statement expression field",
        ));
    };
    match stmt {
        ast::Stmt::Expr(node) if first.field == "value" => clone_expr_from_expr(&node.value, rest),
        ast::Stmt::Assign(node) if first.field == "value" => {
            clone_expr_from_expr(&node.value, rest)
        }
        ast::Stmt::Assign(node) if first.field == "targets" => {
            let target = indexed_expr(&node.targets, first)?;
            clone_expr_from_expr(target, rest)
        }
        ast::Stmt::Delete(node) if first.field == "targets" => {
            let target = indexed_expr(&node.targets, first)?;
            clone_expr_from_expr(target, rest)
        }
        ast::Stmt::Return(node) if first.field == "value" => {
            let value = node
                .value
                .as_ref()
                .ok_or_else(|| crate::errors::schema_error("return expression value is missing"))?;
            clone_expr_from_expr(value, rest)
        }
        ast::Stmt::FunctionDef(node) if first.field == "body" => {
            clone_indexed_expr_from_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::AsyncFunctionDef(node) if first.field == "body" => {
            clone_indexed_expr_from_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::ClassDef(node) if first.field == "body" => {
            clone_indexed_expr_from_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::If(node) if first.field == "body" => {
            clone_indexed_expr_from_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::If(node) if first.field == "orelse" => {
            clone_indexed_expr_from_stmt_list(&node.orelse, first, rest)
        }
        ast::Stmt::For(node) if first.field == "body" => {
            clone_indexed_expr_from_stmt_list(&node.body, first, rest)
        }
        ast::Stmt::For(node) if first.field == "orelse" => {
            clone_indexed_expr_from_stmt_list(&node.orelse, first, rest)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native expression path cannot enter statement field `{}` on {}",
            first.field,
            stmt_kind(stmt)
        ))),
    }
}

fn clone_indexed_expr_from_stmt_list(
    body: &[ast::Stmt],
    segment: &PathSegment,
    rest: &[PathSegment],
) -> PyResult<ast::Expr> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!(
            "{} expression segment requires an index",
            segment.field
        ))
    })?;
    let stmt = body.get(index).ok_or_else(|| {
        crate::errors::schema_error("native expression body index is out of range")
    })?;
    clone_expr_from_stmt(stmt, rest)
}

fn clone_expr_from_expr(expr: &ast::Expr, segments: &[PathSegment]) -> PyResult<ast::Expr> {
    let Some((first, rest)) = segments.split_first() else {
        return Ok(expr.clone());
    };
    match expr {
        ast::Expr::Call(node) if first.field == "func" => clone_expr_from_expr(&node.func, rest),
        ast::Expr::Call(node) if first.field == "args" => {
            let arg = indexed_expr(&node.args, first)?;
            clone_expr_from_expr(arg, rest)
        }
        ast::Expr::Attribute(node) if first.field == "value" => {
            clone_expr_from_expr(&node.value, rest)
        }
        ast::Expr::BinOp(node) if first.field == "left" => clone_expr_from_expr(&node.left, rest),
        ast::Expr::BinOp(node) if first.field == "right" => clone_expr_from_expr(&node.right, rest),
        ast::Expr::Tuple(node) if first.field == "elts" => {
            let item = indexed_expr(&node.elts, first)?;
            clone_expr_from_expr(item, rest)
        }
        ast::Expr::List(node) if first.field == "elts" => {
            let item = indexed_expr(&node.elts, first)?;
            clone_expr_from_expr(item, rest)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native expression path cannot enter field `{}` on {}",
            first.field,
            expr_kind(expr)
        ))),
    }
}

fn clone_function_args_at_path(module: &ast::ModModule, path: &str) -> PyResult<ast::Arguments> {
    let segments = parse_ast_path(path)?;
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "parameter production path must resolve to a function",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native parameter path expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body parameter segment requires an index"))?;
    let stmt = module.body.get(index).ok_or_else(|| {
        crate::errors::schema_error("native parameter body index is out of range")
    })?;
    if !rest.is_empty() {
        return Err(crate::errors::schema_error(
            "parameter production path must point at a function statement",
        ));
    }
    match stmt {
        ast::Stmt::FunctionDef(node) => Ok((*node.args).clone()),
        ast::Stmt::AsyncFunctionDef(node) => Ok((*node.args).clone()),
        _ => Err(crate::errors::schema_error(&format!(
            "native parameter production expected function, got {}",
            stmt_kind(stmt)
        ))),
    }
}

fn clone_funcargs_payload_at_path(
    module: &ast::ModModule,
    path: &str,
) -> PyResult<(Vec<ast::Expr>, Vec<ast::Keyword>)> {
    let expr = clone_expr_at_path(module, path)?;
    match expr {
        ast::Expr::Call(node) if astichi_call_name(&node.func) == Some("astichi_funcargs") => {
            Ok((node.args.clone(), node.keywords.clone()))
        }
        ast::Expr::Call(_) => Err(crate::errors::schema_error(
            "native funcargs production is not astichi_funcargs",
        )),
        _ => Err(crate::errors::schema_error(
            "native funcargs production path did not resolve to a call",
        )),
    }
}

fn replace_expr_at_path(
    module: &mut ast::ModModule,
    path: &str,
    replacement: ast::Expr,
) -> PyResult<()> {
    let segments = parse_ast_path(path)?;
    replace_expr_in_stmt_list(&mut module.body, &segments, replacement)
}

fn replace_expr_in_stmt_list(
    body: &mut [ast::Stmt],
    segments: &[PathSegment],
    replacement: ast::Expr,
) -> PyResult<()> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "expression replacement requires an expression path",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native expression replacement expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body expression segment requires an index"))?;
    let stmt = body.get_mut(index).ok_or_else(|| {
        crate::errors::schema_error("native expression body index is out of range")
    })?;
    replace_expr_in_stmt(stmt, rest, replacement)
}

fn replace_expr_in_stmt(
    stmt: &mut ast::Stmt,
    segments: &[PathSegment],
    replacement: ast::Expr,
) -> PyResult<()> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "expression replacement path must include a statement expression field",
        ));
    };
    match stmt {
        ast::Stmt::Expr(node) if first.field == "value" => {
            replace_boxed_expr(&mut node.value, rest, replacement)
        }
        ast::Stmt::Assign(node) if first.field == "value" => {
            replace_boxed_expr(&mut node.value, rest, replacement)
        }
        ast::Stmt::Assign(node) if first.field == "targets" => {
            replace_indexed_expr(&mut node.targets, first, rest, replacement)
        }
        ast::Stmt::Delete(node) if first.field == "targets" => {
            replace_indexed_expr(&mut node.targets, first, rest, replacement)
        }
        ast::Stmt::Return(node) if first.field == "value" => {
            let value = node
                .value
                .as_mut()
                .ok_or_else(|| crate::errors::schema_error("return expression value is missing"))?;
            replace_boxed_expr(value, rest, replacement)
        }
        ast::Stmt::FunctionDef(node) if first.field == "body" => {
            replace_nested_expr_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::AsyncFunctionDef(node) if first.field == "body" => {
            replace_nested_expr_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::ClassDef(node) if first.field == "body" => {
            replace_nested_expr_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::If(node) if first.field == "body" => {
            replace_nested_expr_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::If(node) if first.field == "orelse" => {
            replace_nested_expr_in_stmt_list(&mut node.orelse, first, rest, replacement)
        }
        ast::Stmt::For(node) if first.field == "body" => {
            replace_nested_expr_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::For(node) if first.field == "orelse" => {
            replace_nested_expr_in_stmt_list(&mut node.orelse, first, rest, replacement)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native expression replacement cannot enter statement field `{}` on {}",
            first.field,
            stmt_kind(stmt)
        ))),
    }
}

fn replace_nested_expr_in_stmt_list(
    body: &mut [ast::Stmt],
    segment: &PathSegment,
    rest: &[PathSegment],
    replacement: ast::Expr,
) -> PyResult<()> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!(
            "{} expression segment requires an index",
            segment.field
        ))
    })?;
    let stmt = body.get_mut(index).ok_or_else(|| {
        crate::errors::schema_error("native expression body index is out of range")
    })?;
    replace_expr_in_stmt(stmt, rest, replacement)
}

fn replace_boxed_expr(
    slot: &mut Box<ast::Expr>,
    rest: &[PathSegment],
    replacement: ast::Expr,
) -> PyResult<()> {
    if rest.is_empty() {
        *slot = Box::new(replacement);
        return Ok(());
    }
    replace_expr_in_expr(slot.as_mut(), rest, replacement)
}

fn replace_indexed_expr(
    items: &mut [ast::Expr],
    segment: &PathSegment,
    rest: &[PathSegment],
    replacement: ast::Expr,
) -> PyResult<()> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!(
            "{} expression segment requires an index",
            segment.field
        ))
    })?;
    let item = items
        .get_mut(index)
        .ok_or_else(|| crate::errors::schema_error("native expression index is out of range"))?;
    if rest.is_empty() {
        *item = replacement;
        return Ok(());
    }
    replace_expr_in_expr(item, rest, replacement)
}

fn replace_expr_in_expr(
    expr: &mut ast::Expr,
    segments: &[PathSegment],
    replacement: ast::Expr,
) -> PyResult<()> {
    let Some((first, rest)) = segments.split_first() else {
        *expr = replacement;
        return Ok(());
    };
    match expr {
        ast::Expr::Call(node) if first.field == "func" => {
            replace_boxed_expr(&mut node.func, rest, replacement)
        }
        ast::Expr::Call(node) if first.field == "args" => {
            replace_indexed_expr(&mut node.args, first, rest, replacement)
        }
        ast::Expr::Attribute(node) if first.field == "value" => {
            replace_boxed_expr(&mut node.value, rest, replacement)
        }
        ast::Expr::BinOp(node) if first.field == "left" => {
            replace_boxed_expr(&mut node.left, rest, replacement)
        }
        ast::Expr::BinOp(node) if first.field == "right" => {
            replace_boxed_expr(&mut node.right, rest, replacement)
        }
        ast::Expr::Tuple(node) if first.field == "elts" => {
            replace_indexed_expr(&mut node.elts, first, rest, replacement)
        }
        ast::Expr::List(node) if first.field == "elts" => {
            replace_indexed_expr(&mut node.elts, first, rest, replacement)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native expression replacement cannot enter field `{}` on {}",
            first.field,
            expr_kind(expr)
        ))),
    }
}

fn splice_parameters_at_path(
    module: &mut ast::ModModule,
    target_path: &str,
    target_name: &str,
    payload_args: ast::Arguments,
) -> PyResult<()> {
    let segments = parse_ast_path(target_path)?;
    if parameter_path_targets_hole(module, &segments, target_name) {
        return splice_parameters_in_stmt_list(&mut module.body, &segments, payload_args);
    }
    let Some(args) =
        find_function_args_with_parameter_hole_in_stmt_list(&mut module.body, target_name)
    else {
        return Err(crate::errors::schema_error(
            "native parameter splice could not find matching parameter hole",
        ));
    };
    splice_payload_into_parameter_hole(args, target_name, payload_args)
}

fn parameter_path_targets_hole(
    module: &ast::ModModule,
    segments: &[PathSegment],
    target_name: &str,
) -> bool {
    let Some(function_segments) = parameter_function_segments(segments) else {
        return false;
    };
    function_args_at_segments(&module.body, function_segments)
        .is_some_and(|args| arguments_have_parameter_hole(args, target_name))
}

fn parameter_function_segments(segments: &[PathSegment]) -> Option<&[PathSegment]> {
    let args_index = segments
        .iter()
        .position(|segment| segment.field == "args")?;
    Some(&segments[..args_index])
}

fn function_args_at_segments<'a>(
    body: &'a [ast::Stmt],
    segments: &[PathSegment],
) -> Option<&'a ast::Arguments> {
    let (first, rest) = segments.split_first()?;
    if first.field != "body" {
        return None;
    }
    let stmt = body.get(first.index?)?;
    function_args_in_stmt_at_segments(stmt, rest)
}

fn function_args_in_stmt_at_segments<'a>(
    stmt: &'a ast::Stmt,
    segments: &[PathSegment],
) -> Option<&'a ast::Arguments> {
    if segments.is_empty() {
        return match stmt {
            ast::Stmt::FunctionDef(node) => Some(&node.args),
            ast::Stmt::AsyncFunctionDef(node) => Some(&node.args),
            _ => None,
        };
    }
    let (first, rest) = segments.split_first()?;
    match stmt {
        ast::Stmt::FunctionDef(node) if first.field == "body" => {
            function_args_at_segments(&node.body, segments)
        }
        ast::Stmt::AsyncFunctionDef(node) if first.field == "body" => {
            function_args_at_segments(&node.body, segments)
        }
        ast::Stmt::ClassDef(node) if first.field == "body" => {
            let child = node.body.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        ast::Stmt::If(node) if first.field == "body" => {
            let child = node.body.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        ast::Stmt::If(node) if first.field == "orelse" => {
            let child = node.orelse.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        ast::Stmt::For(node) if first.field == "body" => {
            let child = node.body.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        ast::Stmt::For(node) if first.field == "orelse" => {
            let child = node.orelse.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        ast::Stmt::AsyncFor(node) if first.field == "body" => {
            let child = node.body.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        ast::Stmt::AsyncFor(node) if first.field == "orelse" => {
            let child = node.orelse.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        ast::Stmt::While(node) if first.field == "body" => {
            let child = node.body.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        ast::Stmt::While(node) if first.field == "orelse" => {
            let child = node.orelse.get(first.index?)?;
            function_args_in_stmt_at_segments(child, rest)
        }
        _ => None,
    }
}

fn splice_parameters_in_stmt_list(
    body: &mut [ast::Stmt],
    segments: &[PathSegment],
    payload_args: ast::Arguments,
) -> PyResult<()> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "parameter splice requires an argument path",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native parameter splice expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body parameter segment requires an index"))?;
    let stmt = body.get_mut(index).ok_or_else(|| {
        crate::errors::schema_error("native parameter body index is out of range")
    })?;
    splice_parameters_in_stmt(stmt, rest, payload_args)
}

fn splice_parameters_in_stmt(
    stmt: &mut ast::Stmt,
    segments: &[PathSegment],
    payload_args: ast::Arguments,
) -> PyResult<()> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "parameter splice requires an argument path",
        ));
    };
    let stmt_name = stmt_kind(stmt);
    match stmt {
        ast::Stmt::FunctionDef(node) => match first.field.as_str() {
            "args" => splice_parameters_in_arguments(&mut node.args, segments, payload_args),
            "body" => {
                splice_parameters_in_nested_stmt_list(&mut node.body, first, rest, payload_args)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native parameter splice cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::AsyncFunctionDef(node) => match first.field.as_str() {
            "args" => splice_parameters_in_arguments(&mut node.args, segments, payload_args),
            "body" => {
                splice_parameters_in_nested_stmt_list(&mut node.body, first, rest, payload_args)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native parameter splice cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::ClassDef(node) => match first.field.as_str() {
            "body" => {
                splice_parameters_in_nested_stmt_list(&mut node.body, first, rest, payload_args)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native parameter splice cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::If(node) => match first.field.as_str() {
            "body" => {
                splice_parameters_in_nested_stmt_list(&mut node.body, first, rest, payload_args)
            }
            "orelse" => {
                splice_parameters_in_nested_stmt_list(&mut node.orelse, first, rest, payload_args)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native parameter splice cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::For(node) => match first.field.as_str() {
            "body" => {
                splice_parameters_in_nested_stmt_list(&mut node.body, first, rest, payload_args)
            }
            "orelse" => {
                splice_parameters_in_nested_stmt_list(&mut node.orelse, first, rest, payload_args)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native parameter splice cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::AsyncFor(node) => match first.field.as_str() {
            "body" => {
                splice_parameters_in_nested_stmt_list(&mut node.body, first, rest, payload_args)
            }
            "orelse" => {
                splice_parameters_in_nested_stmt_list(&mut node.orelse, first, rest, payload_args)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native parameter splice cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::While(node) => match first.field.as_str() {
            "body" => {
                splice_parameters_in_nested_stmt_list(&mut node.body, first, rest, payload_args)
            }
            "orelse" => {
                splice_parameters_in_nested_stmt_list(&mut node.orelse, first, rest, payload_args)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native parameter splice cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        _ => Err(crate::errors::schema_error(&format!(
            "native parameter splice cannot enter statement field `{}` on {}",
            first.field, stmt_name
        ))),
    }
}

fn splice_parameters_in_nested_stmt_list(
    body: &mut [ast::Stmt],
    segment: &PathSegment,
    rest: &[PathSegment],
    payload_args: ast::Arguments,
) -> PyResult<()> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!(
            "{} parameter segment requires an index",
            segment.field
        ))
    })?;
    let stmt = body.get_mut(index).ok_or_else(|| {
        crate::errors::schema_error("native parameter body index is out of range")
    })?;
    splice_parameters_in_stmt(stmt, rest, payload_args)
}

fn find_function_args_with_parameter_hole_in_stmt_list<'a>(
    body: &'a mut [ast::Stmt],
    target_name: &str,
) -> Option<&'a mut Box<ast::Arguments>> {
    for stmt in body {
        match stmt {
            ast::Stmt::FunctionDef(node) => {
                if arguments_have_parameter_hole(&node.args, target_name) {
                    return Some(&mut node.args);
                }
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
            }
            ast::Stmt::AsyncFunctionDef(node) => {
                if arguments_have_parameter_hole(&node.args, target_name) {
                    return Some(&mut node.args);
                }
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
            }
            ast::Stmt::ClassDef(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
            }
            ast::Stmt::If(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
                if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                    &mut node.orelse,
                    target_name,
                ) {
                    return Some(args);
                }
            }
            ast::Stmt::For(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
                if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                    &mut node.orelse,
                    target_name,
                ) {
                    return Some(args);
                }
            }
            ast::Stmt::AsyncFor(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
                if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                    &mut node.orelse,
                    target_name,
                ) {
                    return Some(args);
                }
            }
            ast::Stmt::While(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
                if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                    &mut node.orelse,
                    target_name,
                ) {
                    return Some(args);
                }
            }
            ast::Stmt::With(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
            }
            ast::Stmt::AsyncWith(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
            }
            ast::Stmt::Try(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
                for handler in &mut node.handlers {
                    match handler {
                        ast::ExceptHandler::ExceptHandler(handler) => {
                            if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                                &mut handler.body,
                                target_name,
                            ) {
                                return Some(args);
                            }
                        }
                    }
                }
                if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                    &mut node.orelse,
                    target_name,
                ) {
                    return Some(args);
                }
                if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                    &mut node.finalbody,
                    target_name,
                ) {
                    return Some(args);
                }
            }
            ast::Stmt::TryStar(node) => {
                if let Some(args) =
                    find_function_args_with_parameter_hole_in_stmt_list(&mut node.body, target_name)
                {
                    return Some(args);
                }
                for handler in &mut node.handlers {
                    match handler {
                        ast::ExceptHandler::ExceptHandler(handler) => {
                            if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                                &mut handler.body,
                                target_name,
                            ) {
                                return Some(args);
                            }
                        }
                    }
                }
                if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                    &mut node.orelse,
                    target_name,
                ) {
                    return Some(args);
                }
                if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                    &mut node.finalbody,
                    target_name,
                ) {
                    return Some(args);
                }
            }
            ast::Stmt::Match(node) => {
                for case in &mut node.cases {
                    if let Some(args) = find_function_args_with_parameter_hole_in_stmt_list(
                        &mut case.body,
                        target_name,
                    ) {
                        return Some(args);
                    }
                }
            }
            _ => {}
        }
    }
    None
}

fn arguments_have_parameter_hole(args: &ast::Arguments, target_name: &str) -> bool {
    args.posonlyargs
        .iter()
        .chain(args.args.iter())
        .chain(args.kwonlyargs.iter())
        .any(|arg| is_parameter_hole_for_name(&arg.def.arg, target_name))
}

fn is_parameter_hole_for_name(name: &str, target_name: &str) -> bool {
    name == format!("{target_name}__astichi_param_hole__")
}

fn splice_payload_into_parameter_hole(
    target_args: &mut Box<ast::Arguments>,
    target_name: &str,
    payload_args: ast::Arguments,
) -> PyResult<()> {
    if let Some(index) = target_args
        .posonlyargs
        .iter()
        .position(|arg| is_parameter_hole_for_name(&arg.def.arg, target_name))
    {
        let mut payload_args = payload_args;
        let mut inserted = Vec::new();
        inserted.extend(std::mem::take(&mut payload_args.posonlyargs));
        inserted.extend(std::mem::take(&mut payload_args.args));
        target_args.posonlyargs.splice(index..index + 1, inserted);
        return append_parameter_payload_trailing(target_args, payload_args);
    }
    if let Some(index) = target_args
        .args
        .iter()
        .position(|arg| is_parameter_hole_for_name(&arg.def.arg, target_name))
    {
        let mut payload_args = payload_args;
        let mut inserted = Vec::new();
        inserted.extend(std::mem::take(&mut payload_args.posonlyargs));
        inserted.extend(std::mem::take(&mut payload_args.args));
        target_args.args.splice(index..index + 1, inserted);
        return append_parameter_payload_trailing(target_args, payload_args);
    }
    if let Some(index) = target_args
        .kwonlyargs
        .iter()
        .position(|arg| is_parameter_hole_for_name(&arg.def.arg, target_name))
    {
        let mut payload_args = payload_args;
        target_args.kwonlyargs.splice(
            index..index + 1,
            std::mem::take(&mut payload_args.kwonlyargs),
        );
        append_parameter_payload_trailing(target_args, payload_args)?;
        return Ok(());
    }
    Err(crate::errors::schema_error(
        "native parameter splice could not find matching parameter hole",
    ))
}

fn append_parameter_payload_trailing(
    target_args: &mut Box<ast::Arguments>,
    mut payload_args: ast::Arguments,
) -> PyResult<()> {
    if let Some(vararg) = payload_args.vararg.take() {
        if target_args.vararg.is_some() {
            return Err(crate::errors::schema_error(
                "native parameter splice would create multiple varargs",
            ));
        }
        target_args.vararg = Some(vararg);
    }
    target_args.kwonlyargs.append(&mut payload_args.kwonlyargs);
    if let Some(kwarg) = payload_args.kwarg.take() {
        if target_args.kwarg.is_some() {
            return Err(crate::errors::schema_error(
                "native parameter splice would create multiple kwargs",
            ));
        }
        target_args.kwarg = Some(kwarg);
    }
    Ok(())
}

fn splice_parameters_in_arguments(
    target_args: &mut Box<ast::Arguments>,
    segments: &[PathSegment],
    mut payload_args: ast::Arguments,
) -> PyResult<()> {
    if segments.len() != 2 || segments[0].field != "args" {
        return Err(crate::errors::schema_error(
            "native parameter splice expected args/args[index] path",
        ));
    }
    let target_segment = &segments[1];
    let index = target_segment
        .index
        .ok_or_else(|| crate::errors::schema_error("parameter splice segment requires an index"))?;
    let mut inserted = Vec::new();
    inserted.extend(payload_args.posonlyargs);
    inserted.extend(payload_args.args);
    let vararg = payload_args.vararg.take();
    let kwarg = payload_args.kwarg.take();
    match target_segment.field.as_str() {
        "posonlyargs" => {
            if index >= target_args.posonlyargs.len() {
                return Err(crate::errors::schema_error(
                    "native parameter posonly index is out of range",
                ));
            }
            target_args.posonlyargs.splice(index..index + 1, inserted);
        }
        "args" => {
            if index >= target_args.args.len() {
                return Err(crate::errors::schema_error(
                    "native parameter arg index is out of range",
                ));
            }
            target_args.args.splice(index..index + 1, inserted);
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native parameter splice does not support `{}`",
            target_segment.field
        )))?,
    }
    if let Some(vararg) = vararg {
        if target_args.vararg.is_some() {
            return Err(crate::errors::schema_error(
                "native parameter splice would create multiple varargs",
            ));
        }
        target_args.vararg = Some(vararg);
    }
    target_args.kwonlyargs.append(&mut payload_args.kwonlyargs);
    if let Some(kwarg) = kwarg {
        if target_args.kwarg.is_some() {
            return Err(crate::errors::schema_error(
                "native parameter splice would create multiple kwargs",
            ));
        }
        target_args.kwarg = Some(kwarg);
    }
    Ok(())
}

fn splice_call_arguments_at_path(
    module: &mut ast::ModModule,
    target_path: &str,
    payload_args: Vec<ast::Expr>,
    payload_keywords: Vec<ast::Keyword>,
) -> PyResult<()> {
    let (call_path, arg_kind, arg_index) = call_argument_parent_path(target_path)?;
    match arg_kind {
        CallArgumentKind::Positional => {
            if !payload_keywords.is_empty() {
                return Err(crate::errors::schema_error(
                    "native positional call-argument splice received keyword payloads",
                ));
            }
            let call = call_expr_mut_at_path(module, &call_path)?;
            if arg_index >= call.args.len() {
                return Err(crate::errors::schema_error(
                    "native call argument index is out of range",
                ));
            }
            call.args.splice(arg_index..arg_index + 1, payload_args);
        }
        CallArgumentKind::Keyword => {
            if !payload_args.is_empty() {
                return Err(crate::errors::schema_error(
                    "native keyword call-argument splice received positional payloads",
                ));
            }
            let call = call_expr_mut_at_path(module, &call_path)?;
            if arg_index >= call.keywords.len() {
                return Err(crate::errors::schema_error(
                    "native call keyword index is out of range",
                ));
            }
            call.keywords
                .splice(arg_index..arg_index + 1, payload_keywords);
        }
        CallArgumentKind::SequenceStarred => {
            if !payload_keywords.is_empty() {
                return Err(crate::errors::schema_error(
                    "native sequence call-argument splice received keyword payloads",
                ));
            }
            let elts = sequence_expr_elts_mut_at_path(module, &call_path)?;
            if arg_index >= elts.len() {
                return Err(crate::errors::schema_error(
                    "native sequence argument index is out of range",
                ));
            }
            elts.splice(arg_index..arg_index + 1, payload_args);
        }
    }
    Ok(())
}

enum CallArgumentKind {
    Positional,
    Keyword,
    SequenceStarred,
}

fn call_argument_parent_path(target_path: &str) -> PyResult<(String, CallArgumentKind, usize)> {
    if let Some((prefix, tail)) = target_path.rsplit_once("/args[") {
        let Some(index_text) = tail.strip_suffix("]/value") else {
            return Err(crate::errors::schema_error(
                "native call-argument splice expected starred args[index]/value locator",
            ));
        };
        return Ok((
            prefix.to_string(),
            CallArgumentKind::Positional,
            parse_call_argument_index(index_text)?,
        ));
    }
    if let Some((prefix, tail)) = target_path.rsplit_once("/elts[") {
        let Some(index_text) = tail.strip_suffix("]/value") else {
            return Err(crate::errors::schema_error(
                "native call-argument splice expected starred elts[index]/value locator",
            ));
        };
        return Ok((
            prefix.to_string(),
            CallArgumentKind::SequenceStarred,
            parse_call_argument_index(index_text)?,
        ));
    }
    let Some((prefix, tail)) = target_path.rsplit_once("/keywords[") else {
        return Err(crate::errors::schema_error(
            "native call-argument splice expected args[index], keywords[index], or elts[index] locator",
        ));
    };
    let Some(index_text) = tail.strip_suffix("]/value") else {
        return Err(crate::errors::schema_error(
            "native call-argument splice expected keyword keywords[index]/value locator",
        ));
    };
    Ok((
        prefix.to_string(),
        CallArgumentKind::Keyword,
        parse_call_argument_index(index_text)?,
    ))
}

fn parse_call_argument_index(index_text: &str) -> PyResult<usize> {
    let index = index_text.parse::<usize>().map_err(|_| {
        crate::errors::schema_error("native call-argument index is not an unsigned integer")
    })?;
    Ok(index)
}

fn sequence_expr_elts_mut_at_path<'a>(
    module: &'a mut ast::ModModule,
    path: &str,
) -> PyResult<&'a mut Vec<ast::Expr>> {
    let expr = expr_mut_at_path(module, path)?;
    match expr {
        ast::Expr::Tuple(node) => Ok(&mut node.elts),
        ast::Expr::List(node) => Ok(&mut node.elts),
        _ => Err(crate::errors::schema_error(
            "native sequence call-argument path did not resolve to tuple/list",
        )),
    }
}

fn expr_mut_at_path<'a>(module: &'a mut ast::ModModule, path: &str) -> PyResult<&'a mut ast::Expr> {
    let segments = parse_ast_path(path)?;
    expr_mut_from_stmt_list(&mut module.body, &segments)
}

fn expr_mut_from_stmt_list<'a>(
    body: &'a mut [ast::Stmt],
    segments: &[PathSegment],
) -> PyResult<&'a mut ast::Expr> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "expression path cannot be the module root",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native expression path expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body expression segment requires an index"))?;
    let stmt = body.get_mut(index).ok_or_else(|| {
        crate::errors::schema_error("native expression body index is out of range")
    })?;
    expr_mut_from_stmt(stmt, rest)
}

fn expr_mut_from_stmt<'a>(
    stmt: &'a mut ast::Stmt,
    segments: &[PathSegment],
) -> PyResult<&'a mut ast::Expr> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "expression path must include a statement expression field",
        ));
    };
    let stmt_name = stmt_kind(stmt);
    match stmt {
        ast::Stmt::Expr(node) => match first.field.as_str() {
            "value" => expr_mut_from_boxed_expr(&mut node.value, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::Assign(node) => match first.field.as_str() {
            "value" => expr_mut_from_boxed_expr(&mut node.value, rest),
            "targets" => expr_mut_from_indexed_expr(&mut node.targets, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::Return(node) => match first.field.as_str() {
            "value" => match node.value.as_mut() {
                Some(value) => expr_mut_from_boxed_expr(value, rest),
                None => Err(crate::errors::schema_error(
                    "return expression value is missing",
                )),
            },
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::FunctionDef(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::AsyncFunctionDef(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::ClassDef(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::If(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            "orelse" => expr_mut_from_nested_stmt_list(&mut node.orelse, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::For(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            "orelse" => expr_mut_from_nested_stmt_list(&mut node.orelse, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::AsyncFor(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            "orelse" => expr_mut_from_nested_stmt_list(&mut node.orelse, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::While(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            "orelse" => expr_mut_from_nested_stmt_list(&mut node.orelse, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::With(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::AsyncWith(node) => match first.field.as_str() {
            "body" => expr_mut_from_nested_stmt_list(&mut node.body, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        _ => Err(crate::errors::schema_error(&format!(
            "native expression path cannot enter statement field `{}` on {}",
            first.field, stmt_name
        ))),
    }
}

fn expr_mut_from_nested_stmt_list<'a>(
    body: &'a mut [ast::Stmt],
    segment: &PathSegment,
    rest: &[PathSegment],
) -> PyResult<&'a mut ast::Expr> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!(
            "{} expression segment requires an index",
            segment.field
        ))
    })?;
    let stmt = body.get_mut(index).ok_or_else(|| {
        crate::errors::schema_error("native expression body index is out of range")
    })?;
    expr_mut_from_stmt(stmt, rest)
}

fn expr_mut_from_boxed_expr<'a>(
    slot: &'a mut Box<ast::Expr>,
    rest: &[PathSegment],
) -> PyResult<&'a mut ast::Expr> {
    if rest.is_empty() {
        return Ok(slot.as_mut());
    }
    expr_mut_from_expr(slot.as_mut(), rest)
}

fn expr_mut_from_indexed_expr<'a>(
    items: &'a mut [ast::Expr],
    segment: &PathSegment,
    rest: &[PathSegment],
) -> PyResult<&'a mut ast::Expr> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!(
            "{} expression segment requires an index",
            segment.field
        ))
    })?;
    let item = items
        .get_mut(index)
        .ok_or_else(|| crate::errors::schema_error("native expression index is out of range"))?;
    if rest.is_empty() {
        return Ok(item);
    }
    expr_mut_from_expr(item, rest)
}

fn expr_mut_from_expr<'a>(
    expr: &'a mut ast::Expr,
    segments: &[PathSegment],
) -> PyResult<&'a mut ast::Expr> {
    let Some((first, rest)) = segments.split_first() else {
        return Ok(expr);
    };
    let expr_name = expr_kind(expr);
    match expr {
        ast::Expr::Call(node) => match first.field.as_str() {
            "func" => expr_mut_from_boxed_expr(&mut node.func, rest),
            "args" => expr_mut_from_indexed_expr(&mut node.args, first, rest),
            "keywords" => {
                let index = first.index.ok_or_else(|| {
                    crate::errors::schema_error("call keywords segment requires an index")
                })?;
                let keyword = node.keywords.get_mut(index).ok_or_else(|| {
                    crate::errors::schema_error("native call keyword index is out of range")
                })?;
                expr_mut_from_expr(&mut keyword.value, rest)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter field `{}` on {}",
                first.field, expr_name
            ))),
        },
        ast::Expr::Attribute(node) => match first.field.as_str() {
            "value" => expr_mut_from_boxed_expr(&mut node.value, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter field `{}` on {}",
                first.field, expr_name
            ))),
        },
        ast::Expr::BinOp(node) => match first.field.as_str() {
            "left" => expr_mut_from_boxed_expr(&mut node.left, rest),
            "right" => expr_mut_from_boxed_expr(&mut node.right, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter field `{}` on {}",
                first.field, expr_name
            ))),
        },
        ast::Expr::Tuple(node) => match first.field.as_str() {
            "elts" => expr_mut_from_indexed_expr(&mut node.elts, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter field `{}` on {}",
                first.field, expr_name
            ))),
        },
        ast::Expr::List(node) => match first.field.as_str() {
            "elts" => expr_mut_from_indexed_expr(&mut node.elts, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter field `{}` on {}",
                first.field, expr_name
            ))),
        },
        ast::Expr::Starred(node) => match first.field.as_str() {
            "value" => expr_mut_from_boxed_expr(&mut node.value, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter field `{}` on {}",
                first.field, expr_name
            ))),
        },
        ast::Expr::Subscript(node) => match first.field.as_str() {
            "value" => expr_mut_from_boxed_expr(&mut node.value, rest),
            "slice" => expr_mut_from_boxed_expr(&mut node.slice, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native expression path cannot enter field `{}` on {}",
                first.field, expr_name
            ))),
        },
        _ => Err(crate::errors::schema_error(&format!(
            "native expression path cannot enter field `{}` on {}",
            first.field, expr_name
        ))),
    }
}

fn call_expr_mut_at_path<'a>(
    module: &'a mut ast::ModModule,
    path: &str,
) -> PyResult<&'a mut ast::ExprCall> {
    let segments = parse_ast_path(path)?;
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "call expression path cannot be the module root",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native call path expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body call segment requires an index"))?;
    let stmt = module
        .body
        .get_mut(index)
        .ok_or_else(|| crate::errors::schema_error("native call body index is out of range"))?;
    call_expr_mut_from_stmt(stmt, rest)
}

fn call_expr_mut_from_stmt<'a>(
    stmt: &'a mut ast::Stmt,
    segments: &[PathSegment],
) -> PyResult<&'a mut ast::ExprCall> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "call expression path must include a statement expression field",
        ));
    };
    let stmt_name = stmt_kind(stmt);
    match stmt {
        ast::Stmt::Expr(node) => match first.field.as_str() {
            "value" => call_expr_mut_from_expr(&mut node.value, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::Assign(node) => match first.field.as_str() {
            "value" => call_expr_mut_from_expr(&mut node.value, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::Return(node) => match first.field.as_str() {
            "value" => match node.value.as_mut() {
                Some(value) => call_expr_mut_from_expr(value, rest),
                None => Err(crate::errors::schema_error("return call value is missing")),
            },
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::FunctionDef(node) => match first.field.as_str() {
            "body" => call_expr_mut_from_stmt_list(&mut node.body, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::AsyncFunctionDef(node) => match first.field.as_str() {
            "body" => call_expr_mut_from_stmt_list(&mut node.body, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::ClassDef(node) => match first.field.as_str() {
            "body" => call_expr_mut_from_stmt_list(&mut node.body, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::If(node) => match first.field.as_str() {
            "body" => call_expr_mut_from_stmt_list(&mut node.body, first, rest),
            "orelse" => call_expr_mut_from_stmt_list(&mut node.orelse, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::For(node) => match first.field.as_str() {
            "body" => call_expr_mut_from_stmt_list(&mut node.body, first, rest),
            "orelse" => call_expr_mut_from_stmt_list(&mut node.orelse, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::AsyncFor(node) => match first.field.as_str() {
            "body" => call_expr_mut_from_stmt_list(&mut node.body, first, rest),
            "orelse" => call_expr_mut_from_stmt_list(&mut node.orelse, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        ast::Stmt::While(node) => match first.field.as_str() {
            "body" => call_expr_mut_from_stmt_list(&mut node.body, first, rest),
            "orelse" => call_expr_mut_from_stmt_list(&mut node.orelse, first, rest),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter statement field `{}` on {}",
                first.field, stmt_name
            ))),
        },
        _ => Err(crate::errors::schema_error(&format!(
            "native call path cannot enter statement field `{}` on {}",
            first.field, stmt_name
        ))),
    }
}

fn call_expr_mut_from_stmt_list<'a>(
    body: &'a mut [ast::Stmt],
    segment: &PathSegment,
    rest: &[PathSegment],
) -> PyResult<&'a mut ast::ExprCall> {
    let index = segment.index.ok_or_else(|| {
        crate::errors::schema_error(&format!("{} call segment requires an index", segment.field))
    })?;
    let stmt = body
        .get_mut(index)
        .ok_or_else(|| crate::errors::schema_error("native call body index is out of range"))?;
    call_expr_mut_from_stmt(stmt, rest)
}

fn call_expr_mut_from_expr<'a>(
    expr: &'a mut ast::Expr,
    segments: &[PathSegment],
) -> PyResult<&'a mut ast::ExprCall> {
    let Some((first, rest)) = segments.split_first() else {
        return match expr {
            ast::Expr::Call(node) => Ok(node),
            _ => Err(crate::errors::schema_error(&format!(
                "native call path resolved to {}",
                expr_kind(expr)
            ))),
        };
    };
    let expr_name = expr_kind(expr);
    match expr {
        ast::Expr::Call(node) => match first.field.as_str() {
            "func" => call_expr_mut_from_expr(&mut node.func, rest),
            "args" => {
                let index = first.index.ok_or_else(|| {
                    crate::errors::schema_error("call args segment requires an index")
                })?;
                let arg = node.args.get_mut(index).ok_or_else(|| {
                    crate::errors::schema_error("native call arg index is out of range")
                })?;
                call_expr_mut_from_expr(arg, rest)
            }
            _ => Err(crate::errors::schema_error(&format!(
                "native call path cannot enter field `{}` on {}",
                first.field, expr_name
            ))),
        },
        ast::Expr::Attribute(node) if first.field == "value" => {
            call_expr_mut_from_expr(&mut node.value, rest)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native call path cannot enter field `{}` on {}",
            first.field, expr_name
        ))),
    }
}

fn lower_native_statement_markers_in_module(module: &mut ast::ModModule) -> PyResult<()> {
    lower_native_statement_markers_in_stmt_list(&mut module.body)
}

fn lower_native_statement_markers_in_stmt_list(body: &mut Vec<ast::Stmt>) -> PyResult<()> {
    rename_native_pyimport_collisions(body)?;
    let original = std::mem::take(body);
    for stmt in original {
        body.append(&mut lower_native_statement_markers_in_stmt(stmt)?);
    }
    Ok(())
}

fn rename_native_pyimport_collisions(body: &mut [ast::Stmt]) -> PyResult<()> {
    let import_names = pyimport_final_names_in_stmt_list(body)?;
    if import_names.is_empty() {
        return Ok(());
    }
    let existing = existing_binding_names_for_pyimport_scope(body);
    let mut unavailable = existing
        .union(&import_names)
        .cloned()
        .collect::<BTreeSet<_>>();
    for name in import_names.intersection(&existing) {
        let replacement = fresh_native_scoped_name(name, &unavailable);
        unavailable.insert(replacement.clone());
        rewrite_identifier_in_non_pyimport_stmt_list(body, name, &replacement)?;
    }
    Ok(())
}

fn pyimport_final_names_in_stmt_list(body: &[ast::Stmt]) -> PyResult<BTreeSet<String>> {
    let mut names = BTreeSet::new();
    for stmt in body {
        let ast::Stmt::Expr(node) = stmt else {
            continue;
        };
        for name in pyimport_final_names_from_expr(&node.value)? {
            names.insert(name);
        }
    }
    Ok(names)
}

fn pyimport_final_names_from_expr(expr: &ast::Expr) -> PyResult<Vec<String>> {
    let ast::Expr::Call(call) = expr else {
        return Ok(Vec::new());
    };
    if astichi_call_name(&call.func) != Some("astichi_pyimport") {
        return Ok(Vec::new());
    }
    if let Some(names_expr) = keyword_expr(call, "names") {
        let ast::Expr::Tuple(tuple) = names_expr else {
            return Err(crate::errors::schema_error(
                "native pyimport names must be a tuple of names",
            ));
        };
        return tuple
            .elts
            .iter()
            .map(|item| match item {
                ast::Expr::Name(name) => Ok(name.id.to_string()),
                _ => Err(crate::errors::schema_error(
                    "native pyimport names must contain only names",
                )),
            })
            .collect();
    }
    if let Some(ast::Expr::Name(name)) = keyword_expr(call, "as_") {
        return Ok(vec![name.id.to_string()]);
    }
    let module_expr = keyword_expr(call, "module")
        .ok_or_else(|| crate::errors::schema_error("native pyimport marker is missing module"))?;
    let module_path = dotted_expr_path(module_expr).ok_or_else(|| {
        crate::errors::schema_error("native pyimport module must be a dotted name")
    })?;
    Ok(module_path.into_iter().next().into_iter().collect())
}

fn existing_binding_names_for_pyimport_scope(body: &[ast::Stmt]) -> BTreeSet<String> {
    let mut names = BTreeSet::new();
    for stmt in body {
        collect_existing_binding_names_stmt(stmt, &mut names);
    }
    names
}

fn collect_existing_binding_names_stmt(stmt: &ast::Stmt, names: &mut BTreeSet<String>) {
    match stmt {
        ast::Stmt::Expr(node) if is_pyimport_call_expr(&node.value) => {}
        ast::Stmt::FunctionDef(node) => {
            names.insert(node.name.to_string());
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            names.insert(node.name.to_string());
        }
        ast::Stmt::ClassDef(node) => {
            names.insert(node.name.to_string());
        }
        ast::Stmt::Assign(node) => {
            for target in &node.targets {
                collect_store_binding_names_expr(target, names);
            }
        }
        ast::Stmt::AnnAssign(node) => {
            collect_store_binding_names_expr(&node.target, names);
        }
        ast::Stmt::AugAssign(node) => {
            collect_store_binding_names_expr(&node.target, names);
        }
        ast::Stmt::For(node) => {
            collect_store_binding_names_expr(&node.target, names);
        }
        ast::Stmt::AsyncFor(node) => {
            collect_store_binding_names_expr(&node.target, names);
        }
        ast::Stmt::With(node) => {
            for item in &node.items {
                if let Some(optional_vars) = item.optional_vars.as_ref() {
                    collect_store_binding_names_expr(optional_vars, names);
                }
            }
        }
        ast::Stmt::AsyncWith(node) => {
            for item in &node.items {
                if let Some(optional_vars) = item.optional_vars.as_ref() {
                    collect_store_binding_names_expr(optional_vars, names);
                }
            }
        }
        ast::Stmt::Import(node) => {
            for alias in &node.names {
                names.insert(
                    alias
                        .asname
                        .as_ref()
                        .map(ToString::to_string)
                        .unwrap_or_else(|| {
                            alias
                                .name
                                .split('.')
                                .next()
                                .unwrap_or(alias.name.as_str())
                                .to_string()
                        }),
                );
            }
        }
        ast::Stmt::ImportFrom(node) => {
            for alias in &node.names {
                names.insert(
                    alias
                        .asname
                        .as_ref()
                        .map(ToString::to_string)
                        .unwrap_or_else(|| alias.name.to_string()),
                );
            }
        }
        _ => {}
    }
}

fn collect_store_binding_names_expr(expr: &ast::Expr, names: &mut BTreeSet<String>) {
    match expr {
        ast::Expr::Name(node) => {
            names.insert(node.id.to_string());
        }
        ast::Expr::Tuple(node) => {
            for item in &node.elts {
                collect_store_binding_names_expr(item, names);
            }
        }
        ast::Expr::List(node) => {
            for item in &node.elts {
                collect_store_binding_names_expr(item, names);
            }
        }
        _ => {}
    }
}

fn fresh_native_scoped_name(name: &str, unavailable: &BTreeSet<String>) -> String {
    let mut counter = 1;
    loop {
        let candidate = format!("{name}__astichi_scoped_{counter}");
        if !unavailable.contains(&candidate) {
            return candidate;
        }
        counter += 1;
    }
}

fn rewrite_identifier_in_non_pyimport_stmt_list(
    body: &mut [ast::Stmt],
    authored_name: &str,
    resolved_name: &str,
) -> PyResult<usize> {
    let mut count = 0;
    for stmt in body {
        if matches!(stmt, ast::Stmt::Expr(node) if is_pyimport_call_expr(&node.value)) {
            continue;
        }
        count += rewrite_identifier_in_stmt(stmt, authored_name, resolved_name)?;
    }
    Ok(count)
}

fn lower_native_statement_markers_in_stmt(mut stmt: ast::Stmt) -> PyResult<Vec<ast::Stmt>> {
    match &mut stmt {
        ast::Stmt::Expr(node) => {
            if let Some(mut imports) = pyimport_statements_from_expr(&node.value)? {
                return Ok({
                    for import in &mut imports {
                        lower_native_statement_markers_in_stmt_fields(import)?;
                    }
                    imports
                });
            }
            if is_boundary_call_expr(&node.value) {
                return Ok(Vec::new());
            }
        }
        ast::Stmt::With(node) => {
            for item in &mut node.items {
                lower_literal_refs_in_expr(&mut item.context_expr)?;
                if let Some(optional_vars) = item.optional_vars.as_mut() {
                    lower_literal_refs_in_expr(optional_vars)?;
                }
            }
            lower_native_statement_markers_in_stmt_list(&mut node.body)?;
            if is_defaulted_block_fallback_with(node) {
                return Ok(std::mem::take(&mut node.body));
            }
        }
        _ => {}
    }
    lower_native_statement_markers_in_stmt_fields(&mut stmt)?;
    Ok(vec![stmt])
}

fn lower_native_statement_markers_in_stmt_fields(stmt: &mut ast::Stmt) -> PyResult<()> {
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            strip_unfilled_parameter_holes(&mut node.args);
            lower_native_statement_markers_in_stmt_list(&mut node.body)
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            strip_unfilled_parameter_holes(&mut node.args);
            lower_native_statement_markers_in_stmt_list(&mut node.body)
        }
        ast::Stmt::ClassDef(node) => lower_native_statement_markers_in_stmt_list(&mut node.body),
        ast::Stmt::If(node) => {
            lower_native_statement_markers_in_stmt_list(&mut node.body)?;
            lower_native_statement_markers_in_stmt_list(&mut node.orelse)
        }
        ast::Stmt::For(node) => {
            lower_native_statement_markers_in_stmt_list(&mut node.body)?;
            lower_native_statement_markers_in_stmt_list(&mut node.orelse)
        }
        ast::Stmt::AsyncFor(node) => {
            lower_native_statement_markers_in_stmt_list(&mut node.body)?;
            lower_native_statement_markers_in_stmt_list(&mut node.orelse)
        }
        ast::Stmt::While(node) => {
            lower_native_statement_markers_in_stmt_list(&mut node.body)?;
            lower_native_statement_markers_in_stmt_list(&mut node.orelse)
        }
        ast::Stmt::With(node) => lower_native_statement_markers_in_stmt_list(&mut node.body),
        ast::Stmt::AsyncWith(node) => lower_native_statement_markers_in_stmt_list(&mut node.body),
        ast::Stmt::Try(node) => {
            lower_native_statement_markers_in_stmt_list(&mut node.body)?;
            for handler in &mut node.handlers {
                match handler {
                    ast::ExceptHandler::ExceptHandler(handler) => {
                        lower_native_statement_markers_in_stmt_list(&mut handler.body)?;
                    }
                }
            }
            lower_native_statement_markers_in_stmt_list(&mut node.orelse)?;
            lower_native_statement_markers_in_stmt_list(&mut node.finalbody)
        }
        ast::Stmt::TryStar(node) => {
            lower_native_statement_markers_in_stmt_list(&mut node.body)?;
            for handler in &mut node.handlers {
                match handler {
                    ast::ExceptHandler::ExceptHandler(handler) => {
                        lower_native_statement_markers_in_stmt_list(&mut handler.body)?;
                    }
                }
            }
            lower_native_statement_markers_in_stmt_list(&mut node.orelse)?;
            lower_native_statement_markers_in_stmt_list(&mut node.finalbody)
        }
        ast::Stmt::Match(node) => {
            for case in &mut node.cases {
                lower_native_statement_markers_in_stmt_list(&mut case.body)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn strip_unfilled_parameter_holes(args: &mut ast::Arguments) {
    args.posonlyargs
        .retain(|arg| !is_unfilled_parameter_hole_name(&arg.def.arg));
    args.args
        .retain(|arg| !is_unfilled_parameter_hole_name(&arg.def.arg));
    args.kwonlyargs
        .retain(|arg| !is_unfilled_parameter_hole_name(&arg.def.arg));
}

fn is_unfilled_parameter_hole_name(name: &str) -> bool {
    name.ends_with("__astichi_param_hole__")
}

fn is_defaulted_block_fallback_with(node: &ast::StmtWith) -> bool {
    if node.items.len() != 1 {
        return false;
    }
    let item = &node.items[0];
    let ast::Expr::Call(call) = &item.context_expr else {
        return false;
    };
    if astichi_call_name(&call.func) != Some("astichi_hole") {
        return false;
    }
    matches!(
        item.optional_vars.as_deref(),
        Some(ast::Expr::Name(name)) if name.id.as_str() == "astichi_fallback"
    )
}

fn is_boundary_call_expr(expr: &ast::Expr) -> bool {
    let ast::Expr::Call(call) = expr else {
        return false;
    };
    matches!(
        astichi_call_name(&call.func),
        Some("astichi_pass" | "astichi_import" | "astichi_export")
    )
}

fn pyimport_statements_from_expr(expr: &ast::Expr) -> PyResult<Option<Vec<ast::Stmt>>> {
    let ast::Expr::Call(call) = expr else {
        return Ok(None);
    };
    if !is_pyimport_call_expr(expr) {
        return Ok(None);
    }
    let module_expr = keyword_expr(call, "module")
        .ok_or_else(|| crate::errors::schema_error("native pyimport marker is missing module"))?;
    let module_path = dotted_expr_path(module_expr).ok_or_else(|| {
        crate::errors::schema_error("native pyimport module must be a dotted name")
    })?;
    if let Some(names_expr) = keyword_expr(call, "names") {
        let ast::Expr::Tuple(tuple) = names_expr else {
            return Err(crate::errors::schema_error(
                "native pyimport names must be a tuple of names",
            ));
        };
        let mut aliases = Vec::new();
        for item in &tuple.elts {
            let ast::Expr::Name(name) = item else {
                return Err(crate::errors::schema_error(
                    "native pyimport names must contain only names",
                ));
            };
            aliases.push(ast::Alias {
                range: Default::default(),
                name: ast::Identifier::new(name.id.to_string()),
                asname: None,
            });
        }
        return Ok(Some(vec![ast::Stmt::ImportFrom(ast::StmtImportFrom {
            range: Default::default(),
            module: Some(ast::Identifier::new(module_path.join("."))),
            names: aliases,
            level: Some(ast::Int::new(0)),
        })]));
    }
    let asname = keyword_expr(call, "as_").and_then(|expr| match expr {
        ast::Expr::Name(name) => Some(ast::Identifier::new(name.id.to_string())),
        _ => None,
    });
    Ok(Some(vec![ast::Stmt::Import(ast::StmtImport {
        range: Default::default(),
        names: vec![ast::Alias {
            range: Default::default(),
            name: ast::Identifier::new(module_path.join(".")),
            asname,
        }],
    })]))
}

fn is_pyimport_call_expr(expr: &ast::Expr) -> bool {
    let ast::Expr::Call(call) = expr else {
        return false;
    };
    astichi_call_name(&call.func) == Some("astichi_pyimport")
}

fn keyword_expr<'a>(call: &'a ast::ExprCall, name: &str) -> Option<&'a ast::Expr> {
    call.keywords
        .iter()
        .find(|keyword| keyword.arg.as_deref() == Some(name))
        .map(|keyword| &keyword.value)
}

fn dotted_expr_path(expr: &ast::Expr) -> Option<Vec<String>> {
    match expr {
        ast::Expr::Name(name) => Some(vec![name.id.to_string()]),
        ast::Expr::Attribute(node) => {
            let mut path = dotted_expr_path(&node.value)?;
            path.push(node.attr.to_string());
            Some(path)
        }
        _ => None,
    }
}

fn lower_literal_refs_in_module(module: &mut ast::ModModule) -> PyResult<usize> {
    lower_literal_refs_in_stmt_list(&mut module.body)
}

fn lower_literal_refs_in_stmt_list(body: &mut [ast::Stmt]) -> PyResult<usize> {
    let mut count = 0;
    for stmt in body {
        count += lower_literal_refs_in_stmt(stmt)?;
    }
    Ok(count)
}

fn lower_literal_refs_in_stmt(stmt: &mut ast::Stmt) -> PyResult<usize> {
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            let mut count = lower_literal_refs_in_expr_list(&mut node.decorator_list)?;
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            Ok(count)
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            let mut count = lower_literal_refs_in_expr_list(&mut node.decorator_list)?;
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            Ok(count)
        }
        ast::Stmt::ClassDef(node) => {
            let mut count = lower_literal_refs_in_expr_list(&mut node.decorator_list)?;
            count += lower_literal_refs_in_expr_list(&mut node.bases)?;
            for keyword in &mut node.keywords {
                count += lower_literal_refs_in_expr(&mut keyword.value)?;
            }
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            Ok(count)
        }
        ast::Stmt::Return(node) => match node.value.as_mut() {
            Some(value) => lower_literal_refs_in_expr(value),
            None => Ok(0),
        },
        ast::Stmt::Delete(node) => lower_literal_refs_in_expr_list(&mut node.targets),
        ast::Stmt::Assign(node) => {
            let mut count = lower_literal_refs_in_expr_list(&mut node.targets)?;
            count += lower_literal_refs_in_expr(&mut node.value)?;
            Ok(count)
        }
        ast::Stmt::AugAssign(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.target)?;
            count += lower_literal_refs_in_expr(&mut node.value)?;
            Ok(count)
        }
        ast::Stmt::AnnAssign(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.target)?;
            count += lower_literal_refs_in_expr(&mut node.annotation)?;
            if let Some(value) = node.value.as_mut() {
                count += lower_literal_refs_in_expr(value)?;
            }
            Ok(count)
        }
        ast::Stmt::For(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.target)?;
            count += lower_literal_refs_in_expr(&mut node.iter)?;
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            count += lower_literal_refs_in_stmt_list(&mut node.orelse)?;
            Ok(count)
        }
        ast::Stmt::AsyncFor(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.target)?;
            count += lower_literal_refs_in_expr(&mut node.iter)?;
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            count += lower_literal_refs_in_stmt_list(&mut node.orelse)?;
            Ok(count)
        }
        ast::Stmt::While(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.test)?;
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            count += lower_literal_refs_in_stmt_list(&mut node.orelse)?;
            Ok(count)
        }
        ast::Stmt::If(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.test)?;
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            count += lower_literal_refs_in_stmt_list(&mut node.orelse)?;
            Ok(count)
        }
        ast::Stmt::With(node) => {
            let mut count = 0;
            for item in &mut node.items {
                count += lower_literal_refs_in_expr(&mut item.context_expr)?;
                if let Some(optional_vars) = item.optional_vars.as_mut() {
                    count += lower_literal_refs_in_expr(optional_vars)?;
                }
            }
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            Ok(count)
        }
        ast::Stmt::AsyncWith(node) => {
            let mut count = 0;
            for item in &mut node.items {
                count += lower_literal_refs_in_expr(&mut item.context_expr)?;
                if let Some(optional_vars) = item.optional_vars.as_mut() {
                    count += lower_literal_refs_in_expr(optional_vars)?;
                }
            }
            count += lower_literal_refs_in_stmt_list(&mut node.body)?;
            Ok(count)
        }
        ast::Stmt::Match(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.subject)?;
            for case in &mut node.cases {
                if let Some(guard) = case.guard.as_mut() {
                    count += lower_literal_refs_in_expr(guard)?;
                }
                count += lower_literal_refs_in_stmt_list(&mut case.body)?;
            }
            Ok(count)
        }
        ast::Stmt::Raise(node) => {
            let mut count = 0;
            if let Some(exc) = node.exc.as_mut() {
                count += lower_literal_refs_in_expr(exc)?;
            }
            if let Some(cause) = node.cause.as_mut() {
                count += lower_literal_refs_in_expr(cause)?;
            }
            Ok(count)
        }
        ast::Stmt::Try(node) => {
            let mut count = lower_literal_refs_in_stmt_list(&mut node.body)?;
            for handler in &mut node.handlers {
                match handler {
                    ast::ExceptHandler::ExceptHandler(handler) => {
                        if let Some(type_expr) = handler.type_.as_mut() {
                            count += lower_literal_refs_in_expr(type_expr)?;
                        }
                        count += lower_literal_refs_in_stmt_list(&mut handler.body)?;
                    }
                }
            }
            count += lower_literal_refs_in_stmt_list(&mut node.orelse)?;
            count += lower_literal_refs_in_stmt_list(&mut node.finalbody)?;
            Ok(count)
        }
        ast::Stmt::TryStar(node) => {
            let mut count = lower_literal_refs_in_stmt_list(&mut node.body)?;
            for handler in &mut node.handlers {
                match handler {
                    ast::ExceptHandler::ExceptHandler(handler) => {
                        if let Some(type_expr) = handler.type_.as_mut() {
                            count += lower_literal_refs_in_expr(type_expr)?;
                        }
                        count += lower_literal_refs_in_stmt_list(&mut handler.body)?;
                    }
                }
            }
            count += lower_literal_refs_in_stmt_list(&mut node.orelse)?;
            count += lower_literal_refs_in_stmt_list(&mut node.finalbody)?;
            Ok(count)
        }
        ast::Stmt::Assert(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.test)?;
            if let Some(msg) = node.msg.as_mut() {
                count += lower_literal_refs_in_expr(msg)?;
            }
            Ok(count)
        }
        ast::Stmt::Expr(node) => lower_literal_refs_in_expr(&mut node.value),
        ast::Stmt::TypeAlias(_)
        | ast::Stmt::Import(_)
        | ast::Stmt::ImportFrom(_)
        | ast::Stmt::Global(_)
        | ast::Stmt::Nonlocal(_)
        | ast::Stmt::Pass(_)
        | ast::Stmt::Break(_)
        | ast::Stmt::Continue(_) => Ok(0),
    }
}

fn lower_literal_refs_in_expr_list(items: &mut [ast::Expr]) -> PyResult<usize> {
    let mut count = 0;
    for item in items {
        count += lower_literal_refs_in_expr(item)?;
    }
    Ok(count)
}

fn lower_literal_refs_in_expr(expr: &mut ast::Expr) -> PyResult<usize> {
    if let Some(lowered) = lower_literal_ref_surface(expr)? {
        *expr = lowered;
        return Ok(1);
    }
    if let Some(lowered) = lower_boundary_call_surface(expr)? {
        *expr = lowered;
        return Ok(1);
    }
    match expr {
        ast::Expr::BoolOp(node) => lower_literal_refs_in_expr_list(&mut node.values),
        ast::Expr::NamedExpr(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.target)?;
            count += lower_literal_refs_in_expr(&mut node.value)?;
            Ok(count)
        }
        ast::Expr::BinOp(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.left)?;
            count += lower_literal_refs_in_expr(&mut node.right)?;
            Ok(count)
        }
        ast::Expr::UnaryOp(node) => lower_literal_refs_in_expr(&mut node.operand),
        ast::Expr::Lambda(node) => lower_literal_refs_in_expr(&mut node.body),
        ast::Expr::IfExp(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.test)?;
            count += lower_literal_refs_in_expr(&mut node.body)?;
            count += lower_literal_refs_in_expr(&mut node.orelse)?;
            Ok(count)
        }
        ast::Expr::Dict(node) => {
            let mut count = 0;
            for key in &mut node.keys {
                if let Some(key) = key.as_mut() {
                    count += lower_literal_refs_in_expr(key)?;
                }
            }
            count += lower_literal_refs_in_expr_list(&mut node.values)?;
            Ok(count)
        }
        ast::Expr::Set(node) => lower_literal_refs_in_expr_list(&mut node.elts),
        ast::Expr::ListComp(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.elt)?;
            count += lower_literal_refs_in_comprehensions(&mut node.generators)?;
            Ok(count)
        }
        ast::Expr::SetComp(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.elt)?;
            count += lower_literal_refs_in_comprehensions(&mut node.generators)?;
            Ok(count)
        }
        ast::Expr::GeneratorExp(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.elt)?;
            count += lower_literal_refs_in_comprehensions(&mut node.generators)?;
            Ok(count)
        }
        ast::Expr::DictComp(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.key)?;
            count += lower_literal_refs_in_expr(&mut node.value)?;
            count += lower_literal_refs_in_comprehensions(&mut node.generators)?;
            Ok(count)
        }
        ast::Expr::Await(node) => lower_literal_refs_in_expr(&mut node.value),
        ast::Expr::Yield(node) => match node.value.as_mut() {
            Some(value) => lower_literal_refs_in_expr(value),
            None => Ok(0),
        },
        ast::Expr::YieldFrom(node) => lower_literal_refs_in_expr(&mut node.value),
        ast::Expr::Compare(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.left)?;
            count += lower_literal_refs_in_expr_list(&mut node.comparators)?;
            Ok(count)
        }
        ast::Expr::Call(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.func)?;
            count += lower_literal_refs_in_expr_list(&mut node.args)?;
            for keyword in &mut node.keywords {
                count += lower_literal_refs_in_expr(&mut keyword.value)?;
            }
            Ok(count)
        }
        ast::Expr::FormattedValue(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.value)?;
            if let Some(format_spec) = node.format_spec.as_mut() {
                count += lower_literal_refs_in_expr(format_spec)?;
            }
            Ok(count)
        }
        ast::Expr::JoinedStr(node) => lower_literal_refs_in_expr_list(&mut node.values),
        ast::Expr::Attribute(node) => lower_literal_refs_in_expr(&mut node.value),
        ast::Expr::Subscript(node) => {
            let mut count = lower_literal_refs_in_expr(&mut node.value)?;
            count += lower_literal_refs_in_expr(&mut node.slice)?;
            Ok(count)
        }
        ast::Expr::Starred(node) => lower_literal_refs_in_expr(&mut node.value),
        ast::Expr::List(node) => lower_literal_refs_in_expr_list(&mut node.elts),
        ast::Expr::Tuple(node) => lower_literal_refs_in_expr_list(&mut node.elts),
        ast::Expr::Slice(node) => {
            let mut count = 0;
            if let Some(lower) = node.lower.as_mut() {
                count += lower_literal_refs_in_expr(lower)?;
            }
            if let Some(upper) = node.upper.as_mut() {
                count += lower_literal_refs_in_expr(upper)?;
            }
            if let Some(step) = node.step.as_mut() {
                count += lower_literal_refs_in_expr(step)?;
            }
            Ok(count)
        }
        ast::Expr::Constant(_) | ast::Expr::Name(_) => Ok(0),
    }
}

fn lower_boundary_call_surface(expr: &ast::Expr) -> PyResult<Option<ast::Expr>> {
    match expr {
        ast::Expr::Call(node) if is_boundary_call_expr(expr) => Ok(node.args.first().cloned()),
        ast::Expr::Attribute(node)
            if matches!(node.attr.as_str(), "_" | "astichi_v")
                && matches!(node.value.as_ref(), ast::Expr::Call(_)) =>
        {
            let ast::Expr::Call(call) = node.value.as_ref() else {
                unreachable!("matches checked above");
            };
            if !matches!(
                astichi_call_name(&call.func),
                Some("astichi_pass" | "astichi_import" | "astichi_export")
            ) {
                return Ok(None);
            }
            let Some(mut replacement) = call.args.first().cloned() else {
                return Ok(None);
            };
            set_ref_chain_context(&mut replacement, node.ctx)?;
            Ok(Some(replacement))
        }
        _ => Ok(None),
    }
}

fn lower_literal_refs_in_comprehensions(generators: &mut [ast::Comprehension]) -> PyResult<usize> {
    let mut count = 0;
    for generator in generators {
        count += lower_literal_refs_in_expr(&mut generator.target)?;
        count += lower_literal_refs_in_expr(&mut generator.iter)?;
        count += lower_literal_refs_in_expr_list(&mut generator.ifs)?;
    }
    Ok(count)
}

fn lower_literal_ref_surface(expr: &ast::Expr) -> PyResult<Option<ast::Expr>> {
    match expr {
        ast::Expr::Call(node) if astichi_ref_call_segments(node)?.is_some() => {
            lower_astichi_ref_call(node, ast::ExprContext::Load)
        }
        ast::Expr::Attribute(node)
            if matches!(node.attr.as_str(), "_" | "astichi_v")
                && matches!(node.value.as_ref(), ast::Expr::Call(_)) =>
        {
            let ast::Expr::Call(call) = node.value.as_ref() else {
                unreachable!("matches checked above");
            };
            lower_astichi_ref_call(call, node.ctx)
        }
        _ => Ok(None),
    }
}

fn lower_astichi_ref_call(
    node: &ast::ExprCall,
    ctx: ast::ExprContext,
) -> PyResult<Option<ast::Expr>> {
    let Some(segments) = astichi_ref_call_segments(node)? else {
        return Ok(None);
    };
    if let Some(base) = astichi_ref_call_base(node) {
        return Ok(Some(chain_expr_from_base(base.clone(), &segments, ctx)?));
    }
    Ok(Some(chain_expr(&segments, ctx)?))
}

fn astichi_ref_call_segments(node: &ast::ExprCall) -> PyResult<Option<Vec<String>>> {
    if astichi_call_name(&node.func) != Some("astichi_ref") {
        return Ok(None);
    }
    if node.args.len() != 1 || !node.keywords.is_empty() {
        return Ok(None);
    }
    let Some(raw) = literal_string_expr(&node.args[0]) else {
        return Ok(None);
    };
    let segments = raw.split('.').map(str::to_string).collect::<Vec<_>>();
    if segments.is_empty() || segments.iter().any(|part| !is_ascii_identifier(part)) {
        return Err(crate::errors::schema_error(
            "native literal astichi_ref path is not a valid dotted reference",
        ));
    }
    Ok(Some(segments))
}

fn astichi_ref_call_base(node: &ast::ExprCall) -> Option<&ast::Expr> {
    let ast::Expr::Attribute(func) = node.func.as_ref() else {
        return None;
    };
    if func.attr.as_str() == "astichi_ref" {
        Some(func.value.as_ref())
    } else {
        None
    }
}

fn astichi_call_name(expr: &ast::Expr) -> Option<&str> {
    match expr {
        ast::Expr::Name(node) => Some(node.id.as_str()),
        ast::Expr::Attribute(node) => Some(node.attr.as_str()),
        _ => None,
    }
}

fn literal_string_expr(expr: &ast::Expr) -> Option<String> {
    match expr {
        ast::Expr::Constant(node) => match &node.value {
            ast::Constant::Str(value) => Some(value.to_string()),
            _ => None,
        },
        _ => None,
    }
}

fn is_ascii_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    if first != '_' && !first.is_ascii_alphabetic() {
        return false;
    }
    chars.all(|ch| ch == '_' || ch.is_ascii_alphanumeric())
}

fn chain_expr(segments: &[String], ctx: ast::ExprContext) -> PyResult<ast::Expr> {
    if segments.is_empty() {
        return Err(crate::errors::schema_error(
            "native literal astichi_ref path is empty",
        ));
    }
    let source = format!("{}\n", segments.join("."));
    let module = crate::parser_ir::parse_native_module(&source, "<astichi-ref>")?;
    let mut expr = module
        .body
        .into_iter()
        .next()
        .and_then(|stmt| match stmt {
            ast::Stmt::Expr(node) => Some(*node.value),
            _ => None,
        })
        .ok_or_else(|| crate::errors::schema_error("failed to build native ref chain"))?;
    set_ref_chain_context(&mut expr, ctx)?;
    Ok(expr)
}

fn chain_expr_from_base(
    mut base: ast::Expr,
    segments: &[String],
    ctx: ast::ExprContext,
) -> PyResult<ast::Expr> {
    if segments.is_empty() {
        return Err(crate::errors::schema_error(
            "native literal astichi_ref path is empty",
        ));
    }
    lower_literal_refs_in_expr(&mut base)?;
    force_load_context(&mut base);
    let mut expr = base;
    for (index, segment) in segments.iter().enumerate() {
        let attr_ctx = if index + 1 == segments.len() {
            ctx.clone()
        } else {
            ast::ExprContext::Load
        };
        expr = ast::Expr::Attribute(ast::ExprAttribute {
            range: Default::default(),
            value: Box::new(expr),
            attr: ast::Identifier::new(segment.to_string()),
            ctx: attr_ctx,
        });
    }
    Ok(expr)
}

fn parse_expression_module(source: &str, filename: &str) -> PyResult<ast::Expr> {
    let parse_source = if source.ends_with('\n') {
        source.to_string()
    } else {
        format!("{source}\n")
    };
    let module = crate::parser_ir::parse_native_module(&parse_source, filename)?;
    if module.body.len() != 1 {
        return Err(crate::errors::schema_error(
            "external literal source must contain exactly one expression",
        ));
    }
    match module
        .body
        .into_iter()
        .next()
        .expect("length checked above")
    {
        ast::Stmt::Expr(node) => Ok(*node.value),
        _ => Err(crate::errors::schema_error(
            "external literal source must be an expression",
        )),
    }
}

fn substitute_external_literal_in_module(
    module: &mut ast::ModModule,
    name: &str,
    replacement: &ast::Expr,
) -> PyResult<usize> {
    substitute_external_literal_in_stmt_list(&mut module.body, name, replacement, false)
}

fn substitute_external_literal_in_stmt_list(
    body: &mut Vec<ast::Stmt>,
    name: &str,
    replacement: &ast::Expr,
    shadowed: bool,
) -> PyResult<usize> {
    let mut count = 0;
    let expression_payload_index =
        if body.len() == 1 && !shadowed && matching_bind_external_expr_stmt(&body[0], name) {
            Some(0)
        } else {
            None
        };
    let old_body = std::mem::take(body);
    for (index, mut stmt) in old_body.into_iter().enumerate() {
        if Some(index) != expression_payload_index
            && !shadowed
            && matching_bind_external_expr_stmt(&stmt, name)
        {
            count += 1;
            continue;
        }
        count += substitute_external_literal_in_stmt(&mut stmt, name, replacement, shadowed)?;
        body.push(stmt);
    }
    Ok(count)
}

fn substitute_external_literal_in_stmt(
    stmt: &mut ast::Stmt,
    name: &str,
    replacement: &ast::Expr,
    shadowed: bool,
) -> PyResult<usize> {
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            let mut count = substitute_external_literal_in_expr_list(
                &mut node.decorator_list,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_arguments(
                &mut node.args,
                name,
                replacement,
                shadowed,
            )?;
            if let Some(returns) = node.returns.as_mut() {
                count += substitute_external_literal_in_expr(returns, name, replacement, shadowed)?;
            }
            count += substitute_external_literal_in_type_params(
                &mut node.type_params,
                name,
                replacement,
                shadowed,
            )?;
            let body_shadowed =
                shadowed || function_scope_shadows_name(&node.args, &node.body, name);
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                body_shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            let mut count = substitute_external_literal_in_expr_list(
                &mut node.decorator_list,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_arguments(
                &mut node.args,
                name,
                replacement,
                shadowed,
            )?;
            if let Some(returns) = node.returns.as_mut() {
                count += substitute_external_literal_in_expr(returns, name, replacement, shadowed)?;
            }
            count += substitute_external_literal_in_type_params(
                &mut node.type_params,
                name,
                replacement,
                shadowed,
            )?;
            let body_shadowed =
                shadowed || function_scope_shadows_name(&node.args, &node.body, name);
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                body_shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::ClassDef(node) => {
            let mut count = substitute_external_literal_in_expr_list(
                &mut node.decorator_list,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_expr_list(
                &mut node.bases,
                name,
                replacement,
                shadowed,
            )?;
            for keyword in &mut node.keywords {
                count += substitute_external_literal_in_expr(
                    &mut keyword.value,
                    name,
                    replacement,
                    shadowed,
                )?;
            }
            count += substitute_external_literal_in_type_params(
                &mut node.type_params,
                name,
                replacement,
                shadowed,
            )?;
            let body_shadowed = shadowed || class_scope_shadows_name(&node.body, name);
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                body_shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::Return(node) => match node.value.as_mut() {
            Some(value) => substitute_external_literal_in_expr(value, name, replacement, shadowed),
            None => Ok(0),
        },
        ast::Stmt::Assign(node) => {
            let mut count = substitute_external_literal_in_expr_list(
                &mut node.targets,
                name,
                replacement,
                shadowed,
            )?;
            count +=
                substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)?;
            Ok(count)
        }
        ast::Stmt::Expr(node) => {
            substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)
        }
        ast::Stmt::If(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.test, name, replacement, shadowed)?;
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_stmt_list(
                &mut node.orelse,
                name,
                replacement,
                shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::For(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.target, name, replacement, shadowed)?;
            count +=
                substitute_external_literal_in_expr(&mut node.iter, name, replacement, shadowed)?;
            let body_shadowed = shadowed || target_binds_name(&node.target, name);
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                body_shadowed,
            )?;
            count += substitute_external_literal_in_stmt_list(
                &mut node.orelse,
                name,
                replacement,
                body_shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::AsyncFor(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.target, name, replacement, shadowed)?;
            count +=
                substitute_external_literal_in_expr(&mut node.iter, name, replacement, shadowed)?;
            let body_shadowed = shadowed || target_binds_name(&node.target, name);
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                body_shadowed,
            )?;
            count += substitute_external_literal_in_stmt_list(
                &mut node.orelse,
                name,
                replacement,
                body_shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::Delete(node) => {
            substitute_external_literal_in_expr_list(&mut node.targets, name, replacement, shadowed)
        }
        ast::Stmt::AugAssign(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.target, name, replacement, shadowed)?;
            count +=
                substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)?;
            Ok(count)
        }
        ast::Stmt::AnnAssign(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.target, name, replacement, shadowed)?;
            count += substitute_external_literal_in_expr(
                &mut node.annotation,
                name,
                replacement,
                shadowed,
            )?;
            if let Some(value) = node.value.as_mut() {
                count += substitute_external_literal_in_expr(value, name, replacement, shadowed)?;
            }
            Ok(count)
        }
        ast::Stmt::While(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.test, name, replacement, shadowed)?;
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_stmt_list(
                &mut node.orelse,
                name,
                replacement,
                shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::With(node) => {
            let mut count = 0;
            for item in &mut node.items {
                count += substitute_external_literal_in_expr(
                    &mut item.context_expr,
                    name,
                    replacement,
                    shadowed,
                )?;
                if let Some(optional_vars) = item.optional_vars.as_mut() {
                    count += substitute_external_literal_in_expr(
                        optional_vars,
                        name,
                        replacement,
                        shadowed,
                    )?;
                }
            }
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::AsyncWith(node) => {
            let mut count = 0;
            for item in &mut node.items {
                count += substitute_external_literal_in_expr(
                    &mut item.context_expr,
                    name,
                    replacement,
                    shadowed,
                )?;
                if let Some(optional_vars) = item.optional_vars.as_mut() {
                    count += substitute_external_literal_in_expr(
                        optional_vars,
                        name,
                        replacement,
                        shadowed,
                    )?;
                }
            }
            count += substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::Match(node) => {
            let mut count = substitute_external_literal_in_expr(
                &mut node.subject,
                name,
                replacement,
                shadowed,
            )?;
            for case in &mut node.cases {
                let case_shadowed = shadowed || pattern_binds_name(&case.pattern, name);
                if let Some(guard) = case.guard.as_mut() {
                    count += substitute_external_literal_in_expr(
                        guard,
                        name,
                        replacement,
                        case_shadowed,
                    )?;
                }
                count += substitute_external_literal_in_stmt_list(
                    &mut case.body,
                    name,
                    replacement,
                    case_shadowed,
                )?;
            }
            Ok(count)
        }
        ast::Stmt::Raise(node) => {
            let mut count = 0;
            if let Some(exc) = node.exc.as_mut() {
                count += substitute_external_literal_in_expr(exc, name, replacement, shadowed)?;
            }
            if let Some(cause) = node.cause.as_mut() {
                count += substitute_external_literal_in_expr(cause, name, replacement, shadowed)?;
            }
            Ok(count)
        }
        ast::Stmt::Try(node) => {
            let mut count = substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                shadowed,
            )?;
            for handler in &mut node.handlers {
                match handler {
                    ast::ExceptHandler::ExceptHandler(handler) => {
                        if let Some(type_expr) = handler.type_.as_mut() {
                            count += substitute_external_literal_in_expr(
                                type_expr,
                                name,
                                replacement,
                                shadowed,
                            )?;
                        }
                        let handler_shadowed = shadowed
                            || handler
                                .name
                                .as_ref()
                                .is_some_and(|item| item.as_str() == name);
                        count += substitute_external_literal_in_stmt_list(
                            &mut handler.body,
                            name,
                            replacement,
                            handler_shadowed,
                        )?;
                    }
                }
            }
            count += substitute_external_literal_in_stmt_list(
                &mut node.orelse,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_stmt_list(
                &mut node.finalbody,
                name,
                replacement,
                shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::TryStar(node) => {
            let mut count = substitute_external_literal_in_stmt_list(
                &mut node.body,
                name,
                replacement,
                shadowed,
            )?;
            for handler in &mut node.handlers {
                match handler {
                    ast::ExceptHandler::ExceptHandler(handler) => {
                        if let Some(type_expr) = handler.type_.as_mut() {
                            count += substitute_external_literal_in_expr(
                                type_expr,
                                name,
                                replacement,
                                shadowed,
                            )?;
                        }
                        let handler_shadowed = shadowed
                            || handler
                                .name
                                .as_ref()
                                .is_some_and(|item| item.as_str() == name);
                        count += substitute_external_literal_in_stmt_list(
                            &mut handler.body,
                            name,
                            replacement,
                            handler_shadowed,
                        )?;
                    }
                }
            }
            count += substitute_external_literal_in_stmt_list(
                &mut node.orelse,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_stmt_list(
                &mut node.finalbody,
                name,
                replacement,
                shadowed,
            )?;
            Ok(count)
        }
        ast::Stmt::Assert(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.test, name, replacement, shadowed)?;
            if let Some(msg) = node.msg.as_mut() {
                count += substitute_external_literal_in_expr(msg, name, replacement, shadowed)?;
            }
            Ok(count)
        }
        ast::Stmt::TypeAlias(_)
        | ast::Stmt::Import(_)
        | ast::Stmt::ImportFrom(_)
        | ast::Stmt::Global(_)
        | ast::Stmt::Nonlocal(_)
        | ast::Stmt::Pass(_)
        | ast::Stmt::Break(_)
        | ast::Stmt::Continue(_) => Ok(0),
    }
}

fn substitute_external_literal_in_expr_list(
    items: &mut [ast::Expr],
    name: &str,
    replacement: &ast::Expr,
    shadowed: bool,
) -> PyResult<usize> {
    let mut count = 0;
    for item in items {
        count += substitute_external_literal_in_expr(item, name, replacement, shadowed)?;
    }
    Ok(count)
}

fn substitute_external_literal_in_expr(
    expr: &mut ast::Expr,
    name: &str,
    replacement: &ast::Expr,
    shadowed: bool,
) -> PyResult<usize> {
    if !shadowed && substitute_external_ref_keyword_literal(expr, name, replacement) {
        return Ok(1);
    }
    if !shadowed && (external_bind_expr_matches(expr, name) || load_name_matches(expr, name)) {
        *expr = replacement.clone();
        return Ok(1);
    }
    match expr {
        ast::Expr::BoolOp(node) => {
            substitute_external_literal_in_expr_list(&mut node.values, name, replacement, shadowed)
        }
        ast::Expr::NamedExpr(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.target, name, replacement, shadowed)?;
            count +=
                substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)?;
            Ok(count)
        }
        ast::Expr::BinOp(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.left, name, replacement, shadowed)?;
            count +=
                substitute_external_literal_in_expr(&mut node.right, name, replacement, shadowed)?;
            Ok(count)
        }
        ast::Expr::UnaryOp(node) => {
            substitute_external_literal_in_expr(&mut node.operand, name, replacement, shadowed)
        }
        ast::Expr::Lambda(node) => {
            let mut count = substitute_external_literal_in_arguments(
                &mut node.args,
                name,
                replacement,
                shadowed,
            )?;
            let body_shadowed = shadowed || argument_binds_name(&node.args, name);
            count += substitute_external_literal_in_expr(
                &mut node.body,
                name,
                replacement,
                body_shadowed,
            )?;
            Ok(count)
        }
        ast::Expr::IfExp(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.test, name, replacement, shadowed)?;
            count +=
                substitute_external_literal_in_expr(&mut node.body, name, replacement, shadowed)?;
            count +=
                substitute_external_literal_in_expr(&mut node.orelse, name, replacement, shadowed)?;
            Ok(count)
        }
        ast::Expr::Dict(node) => {
            let mut count = 0;
            for key in &mut node.keys {
                if let Some(key) = key.as_mut() {
                    count += substitute_external_literal_in_expr(key, name, replacement, shadowed)?;
                }
            }
            count += substitute_external_literal_in_expr_list(
                &mut node.values,
                name,
                replacement,
                shadowed,
            )?;
            Ok(count)
        }
        ast::Expr::Set(node) => {
            substitute_external_literal_in_expr_list(&mut node.elts, name, replacement, shadowed)
        }
        ast::Expr::ListComp(node) => {
            let (mut count, added_shadow) = substitute_external_literal_in_comprehensions(
                &mut node.generators,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_expr(
                &mut node.elt,
                name,
                replacement,
                shadowed || added_shadow,
            )?;
            Ok(count)
        }
        ast::Expr::SetComp(node) => {
            let (mut count, added_shadow) = substitute_external_literal_in_comprehensions(
                &mut node.generators,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_expr(
                &mut node.elt,
                name,
                replacement,
                shadowed || added_shadow,
            )?;
            Ok(count)
        }
        ast::Expr::GeneratorExp(node) => {
            let (mut count, added_shadow) = substitute_external_literal_in_comprehensions(
                &mut node.generators,
                name,
                replacement,
                shadowed,
            )?;
            count += substitute_external_literal_in_expr(
                &mut node.elt,
                name,
                replacement,
                shadowed || added_shadow,
            )?;
            Ok(count)
        }
        ast::Expr::DictComp(node) => {
            let (mut count, added_shadow) = substitute_external_literal_in_comprehensions(
                &mut node.generators,
                name,
                replacement,
                shadowed,
            )?;
            let item_shadowed = shadowed || added_shadow;
            count += substitute_external_literal_in_expr(
                &mut node.key,
                name,
                replacement,
                item_shadowed,
            )?;
            count += substitute_external_literal_in_expr(
                &mut node.value,
                name,
                replacement,
                item_shadowed,
            )?;
            Ok(count)
        }
        ast::Expr::Await(node) => {
            substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)
        }
        ast::Expr::Yield(node) => match node.value.as_mut() {
            Some(value) => substitute_external_literal_in_expr(value, name, replacement, shadowed),
            None => Ok(0),
        },
        ast::Expr::YieldFrom(node) => {
            substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)
        }
        ast::Expr::Compare(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.left, name, replacement, shadowed)?;
            count += substitute_external_literal_in_expr_list(
                &mut node.comparators,
                name,
                replacement,
                shadowed,
            )?;
            Ok(count)
        }
        ast::Expr::Call(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.func, name, replacement, shadowed)?;
            count += substitute_external_literal_in_expr_list(
                &mut node.args,
                name,
                replacement,
                shadowed,
            )?;
            for keyword in &mut node.keywords {
                count += substitute_external_literal_in_expr(
                    &mut keyword.value,
                    name,
                    replacement,
                    shadowed,
                )?;
            }
            Ok(count)
        }
        ast::Expr::FormattedValue(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)?;
            if let Some(format_spec) = node.format_spec.as_mut() {
                count +=
                    substitute_external_literal_in_expr(format_spec, name, replacement, shadowed)?;
            }
            Ok(count)
        }
        ast::Expr::JoinedStr(node) => {
            substitute_external_literal_in_expr_list(&mut node.values, name, replacement, shadowed)
        }
        ast::Expr::Attribute(node) => {
            substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)
        }
        ast::Expr::Subscript(node) => {
            let mut count =
                substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)?;
            count +=
                substitute_external_literal_in_expr(&mut node.slice, name, replacement, shadowed)?;
            Ok(count)
        }
        ast::Expr::Starred(node) => {
            substitute_external_literal_in_expr(&mut node.value, name, replacement, shadowed)
        }
        ast::Expr::List(node) => {
            substitute_external_literal_in_expr_list(&mut node.elts, name, replacement, shadowed)
        }
        ast::Expr::Tuple(node) => {
            substitute_external_literal_in_expr_list(&mut node.elts, name, replacement, shadowed)
        }
        ast::Expr::Slice(node) => {
            let mut count = 0;
            if let Some(lower) = node.lower.as_mut() {
                count += substitute_external_literal_in_expr(lower, name, replacement, shadowed)?;
            }
            if let Some(upper) = node.upper.as_mut() {
                count += substitute_external_literal_in_expr(upper, name, replacement, shadowed)?;
            }
            if let Some(step) = node.step.as_mut() {
                count += substitute_external_literal_in_expr(step, name, replacement, shadowed)?;
            }
            Ok(count)
        }
        ast::Expr::Constant(_) | ast::Expr::Name(_) => Ok(0),
    }
}

fn substitute_external_literal_in_comprehensions(
    generators: &mut [ast::Comprehension],
    name: &str,
    replacement: &ast::Expr,
    shadowed: bool,
) -> PyResult<(usize, bool)> {
    let mut count = 0;
    let mut accumulated_shadow = false;
    for generator in generators {
        let generator_input_shadowed = shadowed || accumulated_shadow;
        count += substitute_external_literal_in_expr(
            &mut generator.iter,
            name,
            replacement,
            generator_input_shadowed,
        )?;
        count += substitute_external_literal_in_expr(
            &mut generator.target,
            name,
            replacement,
            generator_input_shadowed,
        )?;
        accumulated_shadow = accumulated_shadow || target_binds_name(&generator.target, name);
        count += substitute_external_literal_in_expr_list(
            &mut generator.ifs,
            name,
            replacement,
            shadowed || accumulated_shadow,
        )?;
    }
    Ok((count, accumulated_shadow))
}

fn substitute_external_ref_keyword_literal(
    expr: &mut ast::Expr,
    name: &str,
    replacement: &ast::Expr,
) -> bool {
    let ast::Expr::Call(node) = expr else {
        return false;
    };
    if astichi_call_name(&node.func) != Some("astichi_ref") {
        return false;
    }
    let Some(index) = node.keywords.iter().position(|keyword| {
        keyword
            .arg
            .as_ref()
            .is_some_and(|arg| arg.as_str() == "external")
    }) else {
        return false;
    };
    let keyword = &node.keywords[index];
    if !external_bind_expr_matches(&keyword.value, name) && !load_name_matches(&keyword.value, name)
    {
        return false;
    }
    node.keywords.remove(index);
    node.args.push(replacement.clone());
    true
}

fn matching_bind_external_expr_stmt(stmt: &ast::Stmt, name: &str) -> bool {
    match stmt {
        ast::Stmt::Expr(node) => external_bind_expr_matches(&node.value, name),
        _ => false,
    }
}

fn substitute_external_literal_in_arguments(
    args: &mut ast::Arguments,
    name: &str,
    replacement: &ast::Expr,
    shadowed: bool,
) -> PyResult<usize> {
    let mut count = 0;
    for arg in args
        .posonlyargs
        .iter_mut()
        .chain(args.args.iter_mut())
        .chain(args.kwonlyargs.iter_mut())
    {
        count += substitute_external_literal_in_arg(&mut arg.def, name, replacement, shadowed)?;
        if let Some(default) = arg.default.as_mut() {
            count += substitute_external_literal_in_expr(default, name, replacement, shadowed)?;
        }
    }
    if let Some(arg) = args.vararg.as_mut() {
        count += substitute_external_literal_in_arg(arg, name, replacement, shadowed)?;
    }
    if let Some(arg) = args.kwarg.as_mut() {
        count += substitute_external_literal_in_arg(arg, name, replacement, shadowed)?;
    }
    Ok(count)
}

fn substitute_external_literal_in_arg(
    arg: &mut ast::Arg,
    name: &str,
    replacement: &ast::Expr,
    shadowed: bool,
) -> PyResult<usize> {
    match arg.annotation.as_mut() {
        Some(annotation) => {
            substitute_external_literal_in_expr(annotation, name, replacement, shadowed)
        }
        None => Ok(0),
    }
}

fn substitute_external_literal_in_type_params(
    type_params: &mut [ast::TypeParam],
    name: &str,
    replacement: &ast::Expr,
    shadowed: bool,
) -> PyResult<usize> {
    let mut count = 0;
    for param in type_params {
        if let ast::TypeParam::TypeVar(node) = param {
            if let Some(bound) = node.bound.as_mut() {
                count += substitute_external_literal_in_expr(bound, name, replacement, shadowed)?;
            }
        }
    }
    Ok(count)
}

fn function_scope_shadows_name(args: &ast::Arguments, body: &[ast::Stmt], name: &str) -> bool {
    argument_binds_name(args, name) || stmt_list_binds_name(body, name)
}

fn class_scope_shadows_name(body: &[ast::Stmt], name: &str) -> bool {
    stmt_list_binds_name(body, name)
}

fn argument_binds_name(args: &ast::Arguments, name: &str) -> bool {
    args.posonlyargs
        .iter()
        .chain(args.args.iter())
        .chain(args.kwonlyargs.iter())
        .any(|arg| arg.def.arg.as_str() == name)
        || args
            .vararg
            .as_ref()
            .is_some_and(|arg| arg.arg.as_str() == name)
        || args
            .kwarg
            .as_ref()
            .is_some_and(|arg| arg.arg.as_str() == name)
}

fn stmt_list_binds_name(body: &[ast::Stmt], name: &str) -> bool {
    body.iter().any(|stmt| stmt_binds_name(stmt, name))
}

fn stmt_binds_name(stmt: &ast::Stmt, name: &str) -> bool {
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            node.name.as_str() == name
                || expr_list_binds_name(&node.decorator_list, name)
                || node
                    .returns
                    .as_ref()
                    .is_some_and(|returns| expr_binds_name(returns, name))
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            node.name.as_str() == name
                || expr_list_binds_name(&node.decorator_list, name)
                || node
                    .returns
                    .as_ref()
                    .is_some_and(|returns| expr_binds_name(returns, name))
        }
        ast::Stmt::ClassDef(node) => {
            node.name.as_str() == name
                || expr_list_binds_name(&node.decorator_list, name)
                || expr_list_binds_name(&node.bases, name)
                || node
                    .keywords
                    .iter()
                    .any(|keyword| expr_binds_name(&keyword.value, name))
        }
        ast::Stmt::Assign(node) => {
            node.targets
                .iter()
                .any(|target| target_binds_name(target, name))
                || expr_binds_name(&node.value, name)
        }
        ast::Stmt::AnnAssign(node) => {
            target_binds_name(&node.target, name)
                || expr_binds_name(&node.annotation, name)
                || node
                    .value
                    .as_ref()
                    .is_some_and(|value| expr_binds_name(value, name))
        }
        ast::Stmt::AugAssign(node) => {
            target_binds_name(&node.target, name) || expr_binds_name(&node.value, name)
        }
        ast::Stmt::Delete(node) => node
            .targets
            .iter()
            .any(|target| target_binds_name(target, name)),
        ast::Stmt::Expr(node) => expr_binds_name(&node.value, name),
        ast::Stmt::Return(node) => node
            .value
            .as_ref()
            .is_some_and(|value| expr_binds_name(value, name)),
        ast::Stmt::For(node) => {
            expr_binds_name(&node.iter, name)
                || stmt_list_binds_name(&node.body, name)
                || stmt_list_binds_name(&node.orelse, name)
        }
        ast::Stmt::AsyncFor(node) => {
            expr_binds_name(&node.iter, name)
                || stmt_list_binds_name(&node.body, name)
                || stmt_list_binds_name(&node.orelse, name)
        }
        ast::Stmt::While(node) => {
            expr_binds_name(&node.test, name)
                || stmt_list_binds_name(&node.body, name)
                || stmt_list_binds_name(&node.orelse, name)
        }
        ast::Stmt::If(node) => {
            expr_binds_name(&node.test, name)
                || stmt_list_binds_name(&node.body, name)
                || stmt_list_binds_name(&node.orelse, name)
        }
        ast::Stmt::With(node) => {
            node.items.iter().any(|item| {
                expr_binds_name(&item.context_expr, name)
                    || item
                        .optional_vars
                        .as_ref()
                        .is_some_and(|optional_vars| target_binds_name(optional_vars, name))
            }) || stmt_list_binds_name(&node.body, name)
        }
        ast::Stmt::AsyncWith(node) => {
            node.items.iter().any(|item| {
                expr_binds_name(&item.context_expr, name)
                    || item
                        .optional_vars
                        .as_ref()
                        .is_some_and(|optional_vars| target_binds_name(optional_vars, name))
            }) || stmt_list_binds_name(&node.body, name)
        }
        ast::Stmt::Try(node) => {
            stmt_list_binds_name(&node.body, name)
                || node.handlers.iter().any(|handler| match handler {
                    ast::ExceptHandler::ExceptHandler(handler) => {
                        handler
                            .type_
                            .as_ref()
                            .is_some_and(|type_| expr_binds_name(type_, name))
                            || stmt_list_binds_name(&handler.body, name)
                    }
                })
                || stmt_list_binds_name(&node.orelse, name)
                || stmt_list_binds_name(&node.finalbody, name)
        }
        ast::Stmt::TryStar(node) => {
            stmt_list_binds_name(&node.body, name)
                || node.handlers.iter().any(|handler| match handler {
                    ast::ExceptHandler::ExceptHandler(handler) => {
                        handler
                            .type_
                            .as_ref()
                            .is_some_and(|type_| expr_binds_name(type_, name))
                            || stmt_list_binds_name(&handler.body, name)
                    }
                })
                || stmt_list_binds_name(&node.orelse, name)
                || stmt_list_binds_name(&node.finalbody, name)
        }
        ast::Stmt::Match(node) => {
            expr_binds_name(&node.subject, name)
                || node.cases.iter().any(|case| {
                    pattern_binds_name(&case.pattern, name)
                        || case
                            .guard
                            .as_ref()
                            .is_some_and(|guard| expr_binds_name(guard, name))
                        || stmt_list_binds_name(&case.body, name)
                })
        }
        ast::Stmt::Raise(node) => {
            node.exc
                .as_ref()
                .is_some_and(|exc| expr_binds_name(exc, name))
                || node
                    .cause
                    .as_ref()
                    .is_some_and(|cause| expr_binds_name(cause, name))
        }
        ast::Stmt::Assert(node) => {
            expr_binds_name(&node.test, name)
                || node
                    .msg
                    .as_ref()
                    .is_some_and(|msg| expr_binds_name(msg, name))
        }
        ast::Stmt::Import(node) => node
            .names
            .iter()
            .any(|alias| import_alias_binds_name(alias, false, name)),
        ast::Stmt::ImportFrom(node) => node
            .names
            .iter()
            .any(|alias| import_alias_binds_name(alias, true, name)),
        ast::Stmt::TypeAlias(node) => {
            target_binds_name(&node.name, name) || expr_binds_name(&node.value, name)
        }
        ast::Stmt::Global(_)
        | ast::Stmt::Nonlocal(_)
        | ast::Stmt::Pass(_)
        | ast::Stmt::Break(_)
        | ast::Stmt::Continue(_) => false,
    }
}

fn expr_list_binds_name(items: &[ast::Expr], name: &str) -> bool {
    items.iter().any(|item| expr_binds_name(item, name))
}

fn expr_binds_name(expr: &ast::Expr, name: &str) -> bool {
    match expr {
        ast::Expr::NamedExpr(node) => {
            target_binds_name(&node.target, name) || expr_binds_name(&node.value, name)
        }
        ast::Expr::BoolOp(node) => expr_list_binds_name(&node.values, name),
        ast::Expr::BinOp(node) => {
            expr_binds_name(&node.left, name) || expr_binds_name(&node.right, name)
        }
        ast::Expr::UnaryOp(node) => expr_binds_name(&node.operand, name),
        ast::Expr::Lambda(_) => false,
        ast::Expr::IfExp(node) => {
            expr_binds_name(&node.test, name)
                || expr_binds_name(&node.body, name)
                || expr_binds_name(&node.orelse, name)
        }
        ast::Expr::Dict(node) => {
            node.keys
                .iter()
                .flatten()
                .any(|key| expr_binds_name(key, name))
                || node.values.iter().any(|value| expr_binds_name(value, name))
        }
        ast::Expr::Set(node) => expr_list_binds_name(&node.elts, name),
        ast::Expr::ListComp(_)
        | ast::Expr::SetComp(_)
        | ast::Expr::DictComp(_)
        | ast::Expr::GeneratorExp(_) => false,
        ast::Expr::Await(node) => expr_binds_name(&node.value, name),
        ast::Expr::Yield(node) => node
            .value
            .as_ref()
            .is_some_and(|value| expr_binds_name(value, name)),
        ast::Expr::YieldFrom(node) => expr_binds_name(&node.value, name),
        ast::Expr::Compare(node) => {
            expr_binds_name(&node.left, name)
                || node
                    .comparators
                    .iter()
                    .any(|comparator| expr_binds_name(comparator, name))
        }
        ast::Expr::Call(node) => {
            expr_binds_name(&node.func, name)
                || node.args.iter().any(|arg| expr_binds_name(arg, name))
                || node
                    .keywords
                    .iter()
                    .any(|keyword| expr_binds_name(&keyword.value, name))
        }
        ast::Expr::FormattedValue(node) => {
            expr_binds_name(&node.value, name)
                || node
                    .format_spec
                    .as_ref()
                    .is_some_and(|format_spec| expr_binds_name(format_spec, name))
        }
        ast::Expr::JoinedStr(node) => expr_list_binds_name(&node.values, name),
        ast::Expr::Attribute(node) => expr_binds_name(&node.value, name),
        ast::Expr::Subscript(node) => {
            expr_binds_name(&node.value, name) || expr_binds_name(&node.slice, name)
        }
        ast::Expr::Starred(node) => expr_binds_name(&node.value, name),
        ast::Expr::List(node) => expr_list_binds_name(&node.elts, name),
        ast::Expr::Tuple(node) => expr_list_binds_name(&node.elts, name),
        ast::Expr::Slice(node) => {
            node.lower
                .as_ref()
                .is_some_and(|lower| expr_binds_name(lower, name))
                || node
                    .upper
                    .as_ref()
                    .is_some_and(|upper| expr_binds_name(upper, name))
                || node
                    .step
                    .as_ref()
                    .is_some_and(|step| expr_binds_name(step, name))
        }
        ast::Expr::Constant(_) | ast::Expr::Name(_) => false,
    }
}

fn target_binds_name(expr: &ast::Expr, name: &str) -> bool {
    match expr {
        ast::Expr::Name(node) => {
            node.id.as_str() == name
                && matches!(node.ctx, ast::ExprContext::Store | ast::ExprContext::Del)
        }
        ast::Expr::Tuple(node) => node.elts.iter().any(|item| target_binds_name(item, name)),
        ast::Expr::List(node) => node.elts.iter().any(|item| target_binds_name(item, name)),
        ast::Expr::Starred(node) => target_binds_name(&node.value, name),
        _ => false,
    }
}

fn pattern_binds_name(pattern: &ast::Pattern, name: &str) -> bool {
    match pattern {
        ast::Pattern::MatchValue(_) | ast::Pattern::MatchSingleton(_) => false,
        ast::Pattern::MatchSequence(node) => node
            .patterns
            .iter()
            .any(|item| pattern_binds_name(item, name)),
        ast::Pattern::MatchMapping(node) => {
            node.rest.as_ref().is_some_and(|rest| rest.as_str() == name)
                || node
                    .patterns
                    .iter()
                    .any(|item| pattern_binds_name(item, name))
        }
        ast::Pattern::MatchClass(node) => {
            node.patterns
                .iter()
                .any(|item| pattern_binds_name(item, name))
                || node
                    .kwd_patterns
                    .iter()
                    .any(|item| pattern_binds_name(item, name))
        }
        ast::Pattern::MatchStar(node) => {
            node.name.as_ref().is_some_and(|item| item.as_str() == name)
        }
        ast::Pattern::MatchAs(node) => {
            node.name.as_ref().is_some_and(|item| item.as_str() == name)
                || node
                    .pattern
                    .as_ref()
                    .is_some_and(|item| pattern_binds_name(item, name))
        }
        ast::Pattern::MatchOr(node) => node
            .patterns
            .iter()
            .any(|item| pattern_binds_name(item, name)),
    }
}

fn import_alias_binds_name(alias: &ast::Alias, from_import: bool, name: &str) -> bool {
    if let Some(asname) = alias.asname.as_ref() {
        return asname.as_str() == name;
    }
    if from_import {
        return alias.name.as_str() == name;
    }
    alias.name.as_str().split('.').next() == Some(name)
}

fn external_bind_expr_matches(expr: &ast::Expr, name: &str) -> bool {
    let ast::Expr::Call(node) = expr else {
        return false;
    };
    if astichi_call_name(&node.func) != Some("astichi_bind_external") {
        return false;
    }
    if node.args.len() != 1 || !node.keywords.is_empty() {
        return false;
    }
    load_name_matches(&node.args[0], name)
}

fn load_name_matches(expr: &ast::Expr, name: &str) -> bool {
    match expr {
        ast::Expr::Name(node) => node.id.as_str() == name && node.ctx == ast::ExprContext::Load,
        _ => false,
    }
}

fn rewrite_identifier_in_module(
    module: &mut ast::ModModule,
    authored_name: &str,
    resolved_name: &str,
) -> PyResult<usize> {
    rewrite_identifier_in_stmt_list(&mut module.body, authored_name, resolved_name)
}

fn rewrite_identifier_in_stmt_list(
    body: &mut [ast::Stmt],
    authored_name: &str,
    resolved_name: &str,
) -> PyResult<usize> {
    let mut count = 0;
    for stmt in body {
        count += rewrite_identifier_in_stmt(stmt, authored_name, resolved_name)?;
    }
    Ok(count)
}

fn rewrite_identifier_in_stmt(
    stmt: &mut ast::Stmt,
    authored_name: &str,
    resolved_name: &str,
) -> PyResult<usize> {
    let mut count = 0;
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            count += rewrite_identifier_text(&mut node.name, authored_name, resolved_name);
            count += rewrite_identifier_in_arguments(&mut node.args, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr_list(
                &mut node.decorator_list,
                authored_name,
                resolved_name,
            )?;
            if let Some(returns) = node.returns.as_mut() {
                count += rewrite_identifier_in_expr(returns, authored_name, resolved_name)?;
            }
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            count += rewrite_identifier_text(&mut node.name, authored_name, resolved_name);
            count += rewrite_identifier_in_arguments(&mut node.args, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr_list(
                &mut node.decorator_list,
                authored_name,
                resolved_name,
            )?;
            if let Some(returns) = node.returns.as_mut() {
                count += rewrite_identifier_in_expr(returns, authored_name, resolved_name)?;
            }
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
        }
        ast::Stmt::ClassDef(node) => {
            count += rewrite_identifier_text(&mut node.name, authored_name, resolved_name);
            count += rewrite_identifier_in_expr_list(
                &mut node.decorator_list,
                authored_name,
                resolved_name,
            )?;
            count +=
                rewrite_identifier_in_expr_list(&mut node.bases, authored_name, resolved_name)?;
            for keyword in &mut node.keywords {
                count +=
                    rewrite_identifier_in_expr(&mut keyword.value, authored_name, resolved_name)?;
            }
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
        }
        ast::Stmt::Return(node) => {
            if let Some(value) = node.value.as_mut() {
                count += rewrite_identifier_in_expr(value, authored_name, resolved_name)?;
            }
        }
        ast::Stmt::Delete(node) => {
            count +=
                rewrite_identifier_in_expr_list(&mut node.targets, authored_name, resolved_name)?;
        }
        ast::Stmt::Assign(node) => {
            count +=
                rewrite_identifier_in_expr_list(&mut node.targets, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Stmt::AugAssign(node) => {
            count += rewrite_identifier_in_expr(&mut node.target, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Stmt::AnnAssign(node) => {
            count += rewrite_identifier_in_expr(&mut node.target, authored_name, resolved_name)?;
            count +=
                rewrite_identifier_in_expr(&mut node.annotation, authored_name, resolved_name)?;
            if let Some(value) = node.value.as_mut() {
                count += rewrite_identifier_in_expr(value, authored_name, resolved_name)?;
            }
        }
        ast::Stmt::For(node) => {
            count += rewrite_identifier_in_expr(&mut node.target, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.iter, authored_name, resolved_name)?;
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
            count +=
                rewrite_identifier_in_stmt_list(&mut node.orelse, authored_name, resolved_name)?;
        }
        ast::Stmt::AsyncFor(node) => {
            count += rewrite_identifier_in_expr(&mut node.target, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.iter, authored_name, resolved_name)?;
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
            count +=
                rewrite_identifier_in_stmt_list(&mut node.orelse, authored_name, resolved_name)?;
        }
        ast::Stmt::While(node) => {
            count += rewrite_identifier_in_expr(&mut node.test, authored_name, resolved_name)?;
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
            count +=
                rewrite_identifier_in_stmt_list(&mut node.orelse, authored_name, resolved_name)?;
        }
        ast::Stmt::If(node) => {
            count += rewrite_identifier_in_expr(&mut node.test, authored_name, resolved_name)?;
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
            count +=
                rewrite_identifier_in_stmt_list(&mut node.orelse, authored_name, resolved_name)?;
        }
        ast::Stmt::Expr(node) => {
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Stmt::With(node) => {
            for item in &mut node.items {
                count += rewrite_identifier_in_expr(
                    &mut item.context_expr,
                    authored_name,
                    resolved_name,
                )?;
                if let Some(optional_vars) = item.optional_vars.as_mut() {
                    count +=
                        rewrite_identifier_in_expr(optional_vars, authored_name, resolved_name)?;
                }
            }
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
        }
        ast::Stmt::AsyncWith(node) => {
            for item in &mut node.items {
                count += rewrite_identifier_in_expr(
                    &mut item.context_expr,
                    authored_name,
                    resolved_name,
                )?;
                if let Some(optional_vars) = item.optional_vars.as_mut() {
                    count +=
                        rewrite_identifier_in_expr(optional_vars, authored_name, resolved_name)?;
                }
            }
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
        }
        ast::Stmt::Raise(node) => {
            if let Some(exc) = node.exc.as_mut() {
                count += rewrite_identifier_in_expr(exc, authored_name, resolved_name)?;
            }
            if let Some(cause) = node.cause.as_mut() {
                count += rewrite_identifier_in_expr(cause, authored_name, resolved_name)?;
            }
        }
        ast::Stmt::Assert(node) => {
            count += rewrite_identifier_in_expr(&mut node.test, authored_name, resolved_name)?;
            if let Some(msg) = node.msg.as_mut() {
                count += rewrite_identifier_in_expr(msg, authored_name, resolved_name)?;
            }
        }
        ast::Stmt::Match(node) => {
            count += rewrite_identifier_in_expr(&mut node.subject, authored_name, resolved_name)?;
            for case in &mut node.cases {
                count +=
                    rewrite_identifier_in_pattern(&mut case.pattern, authored_name, resolved_name);
                if let Some(guard) = case.guard.as_mut() {
                    count += rewrite_identifier_in_expr(guard, authored_name, resolved_name)?;
                }
                count +=
                    rewrite_identifier_in_stmt_list(&mut case.body, authored_name, resolved_name)?;
            }
        }
        ast::Stmt::Try(node) => {
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
            for handler in &mut node.handlers {
                let ast::ExceptHandler::ExceptHandler(handler) = handler;
                if let Some(type_expr) = handler.type_.as_mut() {
                    count += rewrite_identifier_in_expr(type_expr, authored_name, resolved_name)?;
                }
                if let Some(handler_name) = handler.name.as_mut() {
                    count += rewrite_identifier_text(handler_name, authored_name, resolved_name);
                }
                count += rewrite_identifier_in_stmt_list(
                    &mut handler.body,
                    authored_name,
                    resolved_name,
                )?;
            }
            count +=
                rewrite_identifier_in_stmt_list(&mut node.orelse, authored_name, resolved_name)?;
            count +=
                rewrite_identifier_in_stmt_list(&mut node.finalbody, authored_name, resolved_name)?;
        }
        ast::Stmt::TryStar(node) => {
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
            for handler in &mut node.handlers {
                let ast::ExceptHandler::ExceptHandler(handler) = handler;
                if let Some(type_expr) = handler.type_.as_mut() {
                    count += rewrite_identifier_in_expr(type_expr, authored_name, resolved_name)?;
                }
                if let Some(handler_name) = handler.name.as_mut() {
                    count += rewrite_identifier_text(handler_name, authored_name, resolved_name);
                }
                count += rewrite_identifier_in_stmt_list(
                    &mut handler.body,
                    authored_name,
                    resolved_name,
                )?;
            }
            count +=
                rewrite_identifier_in_stmt_list(&mut node.orelse, authored_name, resolved_name)?;
            count +=
                rewrite_identifier_in_stmt_list(&mut node.finalbody, authored_name, resolved_name)?;
        }
        ast::Stmt::TypeAlias(node) => {
            count += rewrite_identifier_in_expr(&mut node.name, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Stmt::Import(node) => {
            for alias in &mut node.names {
                count += rewrite_identifier_in_dotted_text(
                    &mut alias.name,
                    authored_name,
                    resolved_name,
                );
                if let Some(asname) = alias.asname.as_mut() {
                    count += rewrite_identifier_text(asname, authored_name, resolved_name);
                }
            }
        }
        ast::Stmt::ImportFrom(node) => {
            if let Some(module) = node.module.as_mut() {
                count += rewrite_identifier_in_dotted_text(module, authored_name, resolved_name);
            }
            for alias in &mut node.names {
                count += rewrite_identifier_text(&mut alias.name, authored_name, resolved_name);
                if let Some(asname) = alias.asname.as_mut() {
                    count += rewrite_identifier_text(asname, authored_name, resolved_name);
                }
            }
        }
        ast::Stmt::Global(_)
        | ast::Stmt::Nonlocal(_)
        | ast::Stmt::Pass(_)
        | ast::Stmt::Break(_)
        | ast::Stmt::Continue(_) => {}
    }
    Ok(count)
}

fn rewrite_identifier_in_arguments(
    args: &mut Box<ast::Arguments>,
    authored_name: &str,
    resolved_name: &str,
) -> PyResult<usize> {
    let mut count = 0;
    for arg in args
        .posonlyargs
        .iter_mut()
        .chain(args.args.iter_mut())
        .chain(args.kwonlyargs.iter_mut())
    {
        count += rewrite_identifier_text(&mut arg.def.arg, authored_name, resolved_name);
        if let Some(annotation) = arg.def.annotation.as_mut() {
            count += rewrite_identifier_in_expr(annotation, authored_name, resolved_name)?;
        }
        if let Some(default) = arg.default.as_mut() {
            count += rewrite_identifier_in_expr(default, authored_name, resolved_name)?;
        }
    }
    if let Some(arg) = args.vararg.as_mut() {
        count += rewrite_identifier_text(&mut arg.arg, authored_name, resolved_name);
        if let Some(annotation) = arg.annotation.as_mut() {
            count += rewrite_identifier_in_expr(annotation, authored_name, resolved_name)?;
        }
    }
    if let Some(arg) = args.kwarg.as_mut() {
        count += rewrite_identifier_text(&mut arg.arg, authored_name, resolved_name);
        if let Some(annotation) = arg.annotation.as_mut() {
            count += rewrite_identifier_in_expr(annotation, authored_name, resolved_name)?;
        }
    }
    Ok(count)
}

fn rewrite_identifier_in_expr_list(
    items: &mut [ast::Expr],
    authored_name: &str,
    resolved_name: &str,
) -> PyResult<usize> {
    let mut count = 0;
    for item in items {
        count += rewrite_identifier_in_expr(item, authored_name, resolved_name)?;
    }
    Ok(count)
}

fn rewrite_identifier_in_expr(
    expr: &mut ast::Expr,
    authored_name: &str,
    resolved_name: &str,
) -> PyResult<usize> {
    let mut count = 0;
    match expr {
        ast::Expr::Name(node) => {
            count += rewrite_identifier_text(&mut node.id, authored_name, resolved_name);
        }
        ast::Expr::Attribute(node) => {
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Expr::Call(node) => {
            let boundary_arg_matches =
                boundary_identifier_call_argument_matches(node, authored_name);
            count += rewrite_identifier_in_expr(&mut node.func, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr_list(&mut node.args, authored_name, resolved_name)?;
            for keyword in &mut node.keywords {
                if let Some(arg) = keyword.arg.as_mut() {
                    count += rewrite_identifier_text(arg, authored_name, resolved_name);
                }
                count +=
                    rewrite_identifier_in_expr(&mut keyword.value, authored_name, resolved_name)?;
            }
            if boundary_arg_matches {
                set_boundary_explicit_bind_state_native(&mut node.keywords);
            }
        }
        ast::Expr::BinOp(node) => {
            count += rewrite_identifier_in_expr(&mut node.left, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.right, authored_name, resolved_name)?;
        }
        ast::Expr::BoolOp(node) => {
            count +=
                rewrite_identifier_in_expr_list(&mut node.values, authored_name, resolved_name)?;
        }
        ast::Expr::UnaryOp(node) => {
            count += rewrite_identifier_in_expr(&mut node.operand, authored_name, resolved_name)?;
        }
        ast::Expr::IfExp(node) => {
            count += rewrite_identifier_in_expr(&mut node.test, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.body, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.orelse, authored_name, resolved_name)?;
        }
        ast::Expr::Compare(node) => {
            count += rewrite_identifier_in_expr(&mut node.left, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr_list(
                &mut node.comparators,
                authored_name,
                resolved_name,
            )?;
        }
        ast::Expr::List(node) => {
            count += rewrite_identifier_in_expr_list(&mut node.elts, authored_name, resolved_name)?;
        }
        ast::Expr::Tuple(node) => {
            count += rewrite_identifier_in_expr_list(&mut node.elts, authored_name, resolved_name)?;
        }
        ast::Expr::Dict(node) => {
            for key in &mut node.keys {
                if let Some(key) = key.as_mut() {
                    count += rewrite_identifier_in_expr(key, authored_name, resolved_name)?;
                }
            }
            count +=
                rewrite_identifier_in_expr_list(&mut node.values, authored_name, resolved_name)?;
        }
        ast::Expr::Subscript(node) => {
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.slice, authored_name, resolved_name)?;
        }
        ast::Expr::Starred(node) => {
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Expr::NamedExpr(node) => {
            count += rewrite_identifier_in_expr(&mut node.target, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Expr::Lambda(node) => {
            count += rewrite_identifier_in_arguments(&mut node.args, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.body, authored_name, resolved_name)?;
        }
        ast::Expr::Set(node) => {
            count += rewrite_identifier_in_expr_list(&mut node.elts, authored_name, resolved_name)?;
        }
        ast::Expr::ListComp(node) => {
            count += rewrite_identifier_in_expr(&mut node.elt, authored_name, resolved_name)?;
            count += rewrite_identifier_in_comprehensions(
                &mut node.generators,
                authored_name,
                resolved_name,
            )?;
        }
        ast::Expr::SetComp(node) => {
            count += rewrite_identifier_in_expr(&mut node.elt, authored_name, resolved_name)?;
            count += rewrite_identifier_in_comprehensions(
                &mut node.generators,
                authored_name,
                resolved_name,
            )?;
        }
        ast::Expr::GeneratorExp(node) => {
            count += rewrite_identifier_in_expr(&mut node.elt, authored_name, resolved_name)?;
            count += rewrite_identifier_in_comprehensions(
                &mut node.generators,
                authored_name,
                resolved_name,
            )?;
        }
        ast::Expr::DictComp(node) => {
            count += rewrite_identifier_in_expr(&mut node.key, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
            count += rewrite_identifier_in_comprehensions(
                &mut node.generators,
                authored_name,
                resolved_name,
            )?;
        }
        ast::Expr::Await(node) => {
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Expr::Yield(node) => {
            if let Some(value) = node.value.as_mut() {
                count += rewrite_identifier_in_expr(value, authored_name, resolved_name)?;
            }
        }
        ast::Expr::YieldFrom(node) => {
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
        }
        ast::Expr::FormattedValue(node) => {
            count += rewrite_identifier_in_expr(&mut node.value, authored_name, resolved_name)?;
            if let Some(format_spec) = node.format_spec.as_mut() {
                count += rewrite_identifier_in_expr(format_spec, authored_name, resolved_name)?;
            }
        }
        ast::Expr::JoinedStr(node) => {
            count +=
                rewrite_identifier_in_expr_list(&mut node.values, authored_name, resolved_name)?;
        }
        ast::Expr::Slice(node) => {
            if let Some(lower) = node.lower.as_mut() {
                count += rewrite_identifier_in_expr(lower, authored_name, resolved_name)?;
            }
            if let Some(upper) = node.upper.as_mut() {
                count += rewrite_identifier_in_expr(upper, authored_name, resolved_name)?;
            }
            if let Some(step) = node.step.as_mut() {
                count += rewrite_identifier_in_expr(step, authored_name, resolved_name)?;
            }
        }
        ast::Expr::Constant(_) => {}
    }
    Ok(count)
}

fn rewrite_identifier_in_comprehensions(
    generators: &mut [ast::Comprehension],
    authored_name: &str,
    resolved_name: &str,
) -> PyResult<usize> {
    let mut count = 0;
    for generator in generators {
        count += rewrite_identifier_in_expr(&mut generator.target, authored_name, resolved_name)?;
        count += rewrite_identifier_in_expr(&mut generator.iter, authored_name, resolved_name)?;
        count += rewrite_identifier_in_expr_list(&mut generator.ifs, authored_name, resolved_name)?;
    }
    Ok(count)
}

fn rewrite_identifier_in_pattern(
    pattern: &mut ast::Pattern,
    authored_name: &str,
    resolved_name: &str,
) -> usize {
    let mut count = 0;
    match pattern {
        ast::Pattern::MatchValue(node) => {
            if let ast::Expr::Name(name) = node.value.as_mut() {
                count += rewrite_identifier_text(&mut name.id, authored_name, resolved_name);
            }
        }
        ast::Pattern::MatchSingleton(_) => {}
        ast::Pattern::MatchSequence(node) => {
            for item in &mut node.patterns {
                count += rewrite_identifier_in_pattern(item, authored_name, resolved_name);
            }
        }
        ast::Pattern::MatchMapping(node) => {
            if let Some(rest) = node.rest.as_mut() {
                count += rewrite_identifier_text(rest, authored_name, resolved_name);
            }
            for item in &mut node.patterns {
                count += rewrite_identifier_in_pattern(item, authored_name, resolved_name);
            }
        }
        ast::Pattern::MatchClass(node) => {
            if let ast::Expr::Name(name) = node.cls.as_mut() {
                count += rewrite_identifier_text(&mut name.id, authored_name, resolved_name);
            }
            for item in &mut node.patterns {
                count += rewrite_identifier_in_pattern(item, authored_name, resolved_name);
            }
            for item in &mut node.kwd_patterns {
                count += rewrite_identifier_in_pattern(item, authored_name, resolved_name);
            }
        }
        ast::Pattern::MatchStar(node) => {
            if let Some(name) = node.name.as_mut() {
                count += rewrite_identifier_text(name, authored_name, resolved_name);
            }
        }
        ast::Pattern::MatchAs(node) => {
            if let Some(pattern) = node.pattern.as_mut() {
                count += rewrite_identifier_in_pattern(pattern, authored_name, resolved_name);
            }
            if let Some(name) = node.name.as_mut() {
                count += rewrite_identifier_text(name, authored_name, resolved_name);
            }
        }
        ast::Pattern::MatchOr(node) => {
            for item in &mut node.patterns {
                count += rewrite_identifier_in_pattern(item, authored_name, resolved_name);
            }
        }
    }
    count
}

fn rewrite_identifier_text(
    value: &mut ast::Identifier,
    authored_name: &str,
    resolved_name: &str,
) -> usize {
    if identifier_text_matches(value.as_str(), authored_name) {
        *value = resolved_name.into();
        return 1;
    }
    0
}

fn rewrite_identifier_in_dotted_text(
    value: &mut ast::Identifier,
    authored_name: &str,
    resolved_name: &str,
) -> usize {
    let current = value.as_str();
    let mut count = 0;
    let rewritten = current
        .split('.')
        .map(|segment| {
            if identifier_text_matches(segment, authored_name) {
                count += 1;
                resolved_name
            } else {
                segment
            }
        })
        .collect::<Vec<_>>()
        .join(".");
    if count > 0 {
        *value = rewritten.into();
    }
    count
}

fn identifier_text_matches(current: &str, authored_name: &str) -> bool {
    let suffixed = format!("{authored_name}__astichi_arg__");
    current == authored_name || current == suffixed
}

fn boundary_identifier_call_argument_matches(node: &ast::ExprCall, authored_name: &str) -> bool {
    matches!(
        astichi_call_name(&node.func),
        Some("astichi_import" | "astichi_pass")
    ) && node.args.first().is_some_and(|arg| match arg {
        ast::Expr::Name(name) => identifier_text_matches(name.id.as_str(), authored_name),
        _ => false,
    })
}

fn set_boundary_explicit_bind_state_native(keywords: &mut Vec<ast::Keyword>) {
    let mut kept = Vec::new();
    let mut saw_bound = false;
    for mut keyword in std::mem::take(keywords) {
        match keyword.arg.as_ref().map(|item| item.as_str()) {
            Some("outer_bind") => continue,
            Some("bound") => {
                keyword.value = bool_expr(true);
                saw_bound = true;
            }
            _ => {}
        }
        kept.push(keyword);
    }
    if !saw_bound {
        kept.push(ast::Keyword {
            range: Default::default(),
            arg: Some("bound".into()),
            value: bool_expr(true),
        });
    }
    *keywords = kept;
}

fn bool_expr(value: bool) -> ast::Expr {
    ast::Expr::Constant(ast::ExprConstant {
        range: Default::default(),
        value: ast::Constant::Bool(value),
        kind: None,
    })
}

fn set_ref_chain_context(expr: &mut ast::Expr, ctx: ast::ExprContext) -> PyResult<()> {
    match expr {
        ast::Expr::Name(node) => {
            node.ctx = ctx;
            Ok(())
        }
        ast::Expr::Attribute(node) => {
            node.ctx = ctx;
            force_load_context(&mut node.value);
            Ok(())
        }
        _ => Err(crate::errors::schema_error(
            "native ref chain did not parse as a name or attribute",
        )),
    }
}

fn force_load_context(expr: &mut ast::Expr) {
    match expr {
        ast::Expr::Name(node) => {
            node.ctx = ast::ExprContext::Load;
        }
        ast::Expr::Attribute(node) => {
            node.ctx = ast::ExprContext::Load;
            force_load_context(&mut node.value);
        }
        _ => {}
    }
}

fn replace_statement_at_path(
    module: &mut ast::ModModule,
    statement_path: &str,
    replacement: ast::Stmt,
) -> PyResult<()> {
    let segments = parse_ast_path(statement_path)?;
    replace_statement_in_body(&mut module.body, &segments, replacement)
}

fn replace_statements_at_path(
    module: &mut ast::ModModule,
    statement_path: &str,
    replacement: Vec<ast::Stmt>,
) -> PyResult<()> {
    let segments = parse_ast_path(statement_path)?;
    replace_statements_in_body(&mut module.body, &segments, replacement)
}

fn replace_statements_in_body(
    body: &mut Vec<ast::Stmt>,
    segments: &[PathSegment],
    replacement: Vec<ast::Stmt>,
) -> PyResult<()> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "statement splice requires a statement path",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native statement splice expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body splice segment requires an index"))?;
    if rest.is_empty() {
        if index >= body.len() {
            return Err(crate::errors::schema_error(
                "native splice body index is out of range",
            ));
        }
        body.splice(index..index + 1, replacement);
        return Ok(());
    }
    let stmt = body
        .get_mut(index)
        .ok_or_else(|| crate::errors::schema_error("native splice body index is out of range"))?;
    replace_statements_in_stmt(stmt, rest, replacement)
}

fn replace_statements_in_stmt(
    stmt: &mut ast::Stmt,
    segments: &[PathSegment],
    replacement: Vec<ast::Stmt>,
) -> PyResult<()> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "statement splice requires a statement path",
        ));
    };
    match stmt {
        ast::Stmt::FunctionDef(node) if first.field == "body" => {
            replace_statements_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::AsyncFunctionDef(node) if first.field == "body" => {
            replace_statements_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::ClassDef(node) if first.field == "body" => {
            replace_statements_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::If(node) if first.field == "body" => {
            replace_statements_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::If(node) if first.field == "orelse" => {
            replace_statements_in_stmt_list(&mut node.orelse, first, rest, replacement)
        }
        ast::Stmt::For(node) if first.field == "body" => {
            replace_statements_in_stmt_list(&mut node.body, first, rest, replacement)
        }
        ast::Stmt::For(node) if first.field == "orelse" => {
            replace_statements_in_stmt_list(&mut node.orelse, first, rest, replacement)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native statement splice cannot enter field `{}` on {}",
            first.field,
            stmt_kind(stmt)
        ))),
    }
}

fn replace_statements_in_stmt_list(
    body: &mut Vec<ast::Stmt>,
    segment: &PathSegment,
    rest: &[PathSegment],
    replacement: Vec<ast::Stmt>,
) -> PyResult<()> {
    let index = segment
        .index
        .ok_or_else(|| crate::errors::schema_error("statement splice segment requires an index"))?;
    if rest.is_empty() {
        if index >= body.len() {
            return Err(crate::errors::schema_error(
                "native splice body index is out of range",
            ));
        }
        body.splice(index..index + 1, replacement);
        return Ok(());
    }
    let stmt = body
        .get_mut(index)
        .ok_or_else(|| crate::errors::schema_error("native splice body index is out of range"))?;
    replace_statements_in_stmt(stmt, rest, replacement)
}

fn replace_statement_in_body(
    body: &mut [ast::Stmt],
    segments: &[PathSegment],
    replacement: ast::Stmt,
) -> PyResult<()> {
    let Some((first, rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "statement replacement requires a statement path",
        ));
    };
    if first.field != "body" {
        return Err(crate::errors::schema_error(&format!(
            "native statement replacement expected body segment, got `{}`",
            first.field
        )));
    }
    let index = first
        .index
        .ok_or_else(|| crate::errors::schema_error("body replacement segment requires an index"))?;
    if rest.is_empty() {
        let slot = body.get_mut(index).ok_or_else(|| {
            crate::errors::schema_error("native replacement body index is out of range")
        })?;
        *slot = replacement;
        return Ok(());
    }
    let stmt = body.get_mut(index).ok_or_else(|| {
        crate::errors::schema_error("native replacement body index is out of range")
    })?;
    replace_statement_in_stmt(stmt, rest, replacement)
}

fn replace_statement_in_stmt(
    stmt: &mut ast::Stmt,
    segments: &[PathSegment],
    replacement: ast::Stmt,
) -> PyResult<()> {
    let Some((first, _rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "statement replacement requires a statement path",
        ));
    };
    match stmt {
        ast::Stmt::FunctionDef(node) if first.field == "body" => {
            replace_statement_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::AsyncFunctionDef(node) if first.field == "body" => {
            replace_statement_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::ClassDef(node) if first.field == "body" => {
            replace_statement_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::If(node) if first.field == "body" => {
            replace_statement_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::If(node) if first.field == "orelse" => {
            replace_statement_in_body(&mut node.orelse, segments, replacement)
        }
        ast::Stmt::For(node) if first.field == "body" => {
            replace_statement_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::For(node) if first.field == "orelse" => {
            replace_statement_in_body(&mut node.orelse, segments, replacement)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native statement replacement cannot enter field `{}` on {}",
            first.field,
            stmt_kind(stmt)
        ))),
    }
}

fn stmt_kind(stmt: &ast::Stmt) -> &'static str {
    match stmt {
        ast::Stmt::FunctionDef(_) => "FunctionDef",
        ast::Stmt::AsyncFunctionDef(_) => "AsyncFunctionDef",
        ast::Stmt::ClassDef(_) => "ClassDef",
        ast::Stmt::Return(_) => "Return",
        ast::Stmt::Delete(_) => "Delete",
        ast::Stmt::Assign(_) => "Assign",
        ast::Stmt::TypeAlias(_) => "TypeAlias",
        ast::Stmt::AugAssign(_) => "AugAssign",
        ast::Stmt::AnnAssign(_) => "AnnAssign",
        ast::Stmt::For(_) => "For",
        ast::Stmt::AsyncFor(_) => "AsyncFor",
        ast::Stmt::While(_) => "While",
        ast::Stmt::If(_) => "If",
        ast::Stmt::With(_) => "With",
        ast::Stmt::AsyncWith(_) => "AsyncWith",
        ast::Stmt::Match(_) => "Match",
        ast::Stmt::Raise(_) => "Raise",
        ast::Stmt::Try(_) => "Try",
        ast::Stmt::TryStar(_) => "TryStar",
        ast::Stmt::Assert(_) => "Assert",
        ast::Stmt::Import(_) => "Import",
        ast::Stmt::ImportFrom(_) => "ImportFrom",
        ast::Stmt::Global(_) => "Global",
        ast::Stmt::Nonlocal(_) => "Nonlocal",
        ast::Stmt::Expr(_) => "Expr",
        ast::Stmt::Pass(_) => "Pass",
        ast::Stmt::Break(_) => "Break",
        ast::Stmt::Continue(_) => "Continue",
    }
}

fn expr_kind(expr: &ast::Expr) -> &'static str {
    match expr {
        ast::Expr::BoolOp(_) => "BoolOp",
        ast::Expr::NamedExpr(_) => "NamedExpr",
        ast::Expr::BinOp(_) => "BinOp",
        ast::Expr::UnaryOp(_) => "UnaryOp",
        ast::Expr::Lambda(_) => "Lambda",
        ast::Expr::IfExp(_) => "IfExp",
        ast::Expr::Dict(_) => "Dict",
        ast::Expr::Set(_) => "Set",
        ast::Expr::ListComp(_) => "ListComp",
        ast::Expr::SetComp(_) => "SetComp",
        ast::Expr::GeneratorExp(_) => "GeneratorExp",
        ast::Expr::DictComp(_) => "DictComp",
        ast::Expr::Await(_) => "Await",
        ast::Expr::Yield(_) => "Yield",
        ast::Expr::YieldFrom(_) => "YieldFrom",
        ast::Expr::Compare(_) => "Compare",
        ast::Expr::Call(_) => "Call",
        ast::Expr::FormattedValue(_) => "FormattedValue",
        ast::Expr::JoinedStr(_) => "JoinedStr",
        ast::Expr::Constant(_) => "Constant",
        ast::Expr::Attribute(_) => "Attribute",
        ast::Expr::Subscript(_) => "Subscript",
        ast::Expr::Starred(_) => "Starred",
        ast::Expr::Name(_) => "Name",
        ast::Expr::List(_) => "List",
        ast::Expr::Tuple(_) => "Tuple",
        ast::Expr::Slice(_) => "Slice",
    }
}
