use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};
use rustpython_parser::ast;

use crate::handles::EngineHandle;
use crate::occurrence_store::{
    NativeAssemblyStateHandle, NativeEdgeHandle, NativeOverlayHandle, NativeTemplateHandle,
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
    let (target_path, payload_args) = {
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
        let source_occurrence = state_ref.occurrence(edge_ref.source_occurrence_index())?;
        let source_template = engine.template(source_occurrence.template_index())?;
        let source_module = source_template.module().ok_or_else(|| {
            crate::errors::schema_error("native source template does not carry native parser IR")
        })?;
        let source_path = source_template
            .unique_locator_ast_path_for_surface("astichi.surface.parameter.production")?;
        let payload_args = clone_function_args_at_path(source_module, source_path)?;
        (target_path, payload_args)
    };
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    splice_parameters_at_path(workspace_ref.module_mut(), &target_path, payload_args)
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
        if overlay_ref.kind() != "identifier" {
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
        (
            record.resource_name().to_string(),
            overlay_ref.source_label().to_string(),
        )
    };
    let workspace_ref = engine.workspace_mut(workspace.index)?;
    rewrite_identifier_in_module(workspace_ref.module_mut(), &authored_name, &resolved_name)
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
    payload_args: ast::Arguments,
) -> PyResult<()> {
    let segments = parse_ast_path(target_path)?;
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
    let stmt = module.body.get_mut(index).ok_or_else(|| {
        crate::errors::schema_error("native parameter body index is out of range")
    })?;
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            splice_parameters_in_arguments(&mut node.args, rest, payload_args)
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            splice_parameters_in_arguments(&mut node.args, rest, payload_args)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native parameter splice expected function, got {}",
            stmt_kind(stmt)
        ))),
    }
}

fn splice_parameters_in_arguments(
    target_args: &mut Box<ast::Arguments>,
    segments: &[PathSegment],
    payload_args: ast::Arguments,
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
    if payload_args.vararg.is_some()
        || !payload_args.kwonlyargs.is_empty()
        || payload_args.kwarg.is_some()
    {
        return Err(crate::errors::schema_error(
            "native parameter splice primitive only supports positional payloads",
        ));
    }
    match target_segment.field.as_str() {
        "posonlyargs" => {
            if index >= target_args.posonlyargs.len() {
                return Err(crate::errors::schema_error(
                    "native parameter posonly index is out of range",
                ));
            }
            target_args.posonlyargs.splice(index..index + 1, inserted);
            Ok(())
        }
        "args" => {
            if index >= target_args.args.len() {
                return Err(crate::errors::schema_error(
                    "native parameter arg index is out of range",
                ));
            }
            target_args.args.splice(index..index + 1, inserted);
            Ok(())
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native parameter splice does not support `{}`",
            target_segment.field
        ))),
    }
}

fn splice_call_arguments_at_path(
    module: &mut ast::ModModule,
    target_path: &str,
    payload_args: Vec<ast::Expr>,
    payload_keywords: Vec<ast::Keyword>,
) -> PyResult<()> {
    let (call_path, arg_index) = call_argument_parent_path(target_path)?;
    let call = call_expr_mut_at_path(module, &call_path)?;
    if !payload_keywords.is_empty() {
        return Err(crate::errors::schema_error(
            "native call-argument splice primitive only supports positional payloads",
        ));
    }
    if arg_index >= call.args.len() {
        return Err(crate::errors::schema_error(
            "native call argument index is out of range",
        ));
    }
    call.args.splice(arg_index..arg_index + 1, payload_args);
    Ok(())
}

fn call_argument_parent_path(target_path: &str) -> PyResult<(String, usize)> {
    let Some((prefix, tail)) = target_path.rsplit_once("/args[") else {
        return Err(crate::errors::schema_error(
            "native call-argument splice expected args[index] locator",
        ));
    };
    let Some(index_text) = tail.strip_suffix("]/value") else {
        return Err(crate::errors::schema_error(
            "native call-argument splice expected starred args[index]/value locator",
        ));
    };
    let index = index_text.parse::<usize>().map_err(|_| {
        crate::errors::schema_error("native call-argument index is not an unsigned integer")
    })?;
    Ok((prefix.to_string(), index))
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
        ast::Stmt::Expr(node) if first.field == "value" => {
            call_expr_mut_from_expr(&mut node.value, rest)
        }
        ast::Stmt::Assign(node) if first.field == "value" => {
            call_expr_mut_from_expr(&mut node.value, rest)
        }
        ast::Stmt::Return(node) if first.field == "value" => match node.value.as_mut() {
            Some(value) => call_expr_mut_from_expr(value, rest),
            None => Err(crate::errors::schema_error("return call value is missing")),
        },
        _ => Err(crate::errors::schema_error(&format!(
            "native call path cannot enter statement field `{}` on {}",
            first.field, stmt_name
        ))),
    }
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
            let segments = astichi_ref_call_segments(node)?.expect("checked is_some");
            Ok(Some(chain_expr(&segments, ast::ExprContext::Load)?))
        }
        ast::Expr::Attribute(node)
            if matches!(node.attr.as_str(), "_" | "astichi_v")
                && matches!(node.value.as_ref(), ast::Expr::Call(_)) =>
        {
            let ast::Expr::Call(call) = node.value.as_ref() else {
                unreachable!("matches checked above");
            };
            match astichi_ref_call_segments(call)? {
                Some(segments) => Ok(Some(chain_expr(&segments, node.ctx)?)),
                None => Ok(None),
            }
        }
        _ => Ok(None),
    }
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
            count += rewrite_identifier_in_arguments(&mut node.args, authored_name, resolved_name);
            count += rewrite_identifier_in_expr_list(
                &mut node.decorator_list,
                authored_name,
                resolved_name,
            )?;
            count += rewrite_identifier_in_stmt_list(&mut node.body, authored_name, resolved_name)?;
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            count += rewrite_identifier_text(&mut node.name, authored_name, resolved_name);
            count += rewrite_identifier_in_arguments(&mut node.args, authored_name, resolved_name);
            count += rewrite_identifier_in_expr_list(
                &mut node.decorator_list,
                authored_name,
                resolved_name,
            )?;
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
        ast::Stmt::Match(_)
        | ast::Stmt::Try(_)
        | ast::Stmt::TryStar(_)
        | ast::Stmt::TypeAlias(_)
        | ast::Stmt::Import(_)
        | ast::Stmt::ImportFrom(_)
        | ast::Stmt::Global(_)
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
) -> usize {
    let mut count = 0;
    for arg in args
        .posonlyargs
        .iter_mut()
        .chain(args.args.iter_mut())
        .chain(args.kwonlyargs.iter_mut())
    {
        count += rewrite_identifier_text(&mut arg.def.arg, authored_name, resolved_name);
    }
    if let Some(arg) = args.vararg.as_mut() {
        count += rewrite_identifier_text(&mut arg.arg, authored_name, resolved_name);
    }
    if let Some(arg) = args.kwarg.as_mut() {
        count += rewrite_identifier_text(&mut arg.arg, authored_name, resolved_name);
    }
    count
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
            count += rewrite_identifier_in_expr(&mut node.func, authored_name, resolved_name)?;
            count += rewrite_identifier_in_expr_list(&mut node.args, authored_name, resolved_name)?;
            for keyword in &mut node.keywords {
                count +=
                    rewrite_identifier_in_expr(&mut keyword.value, authored_name, resolved_name)?;
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
        ast::Expr::Constant(_)
        | ast::Expr::NamedExpr(_)
        | ast::Expr::Lambda(_)
        | ast::Expr::Set(_)
        | ast::Expr::ListComp(_)
        | ast::Expr::SetComp(_)
        | ast::Expr::GeneratorExp(_)
        | ast::Expr::DictComp(_)
        | ast::Expr::Await(_)
        | ast::Expr::Yield(_)
        | ast::Expr::YieldFrom(_)
        | ast::Expr::FormattedValue(_)
        | ast::Expr::JoinedStr(_) => {}
    }
    Ok(count)
}

fn rewrite_identifier_text(
    value: &mut ast::Identifier,
    authored_name: &str,
    resolved_name: &str,
) -> usize {
    let current = value.as_str();
    let suffixed = format!("{authored_name}__astichi_arg__");
    if current == authored_name || current == suffixed {
        *value = resolved_name.into();
        return 1;
    }
    0
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
    let Some((first, _rest)) = segments.split_first() else {
        return Err(crate::errors::schema_error(
            "statement splice requires a statement path",
        ));
    };
    match stmt {
        ast::Stmt::FunctionDef(node) if first.field == "body" => {
            replace_statements_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::AsyncFunctionDef(node) if first.field == "body" => {
            replace_statements_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::ClassDef(node) if first.field == "body" => {
            replace_statements_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::If(node) if first.field == "body" => {
            replace_statements_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::If(node) if first.field == "orelse" => {
            replace_statements_in_body(&mut node.orelse, segments, replacement)
        }
        ast::Stmt::For(node) if first.field == "body" => {
            replace_statements_in_body(&mut node.body, segments, replacement)
        }
        ast::Stmt::For(node) if first.field == "orelse" => {
            replace_statements_in_body(&mut node.orelse, segments, replacement)
        }
        _ => Err(crate::errors::schema_error(&format!(
            "native statement splice cannot enter field `{}` on {}",
            first.field,
            stmt_kind(stmt)
        ))),
    }
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
