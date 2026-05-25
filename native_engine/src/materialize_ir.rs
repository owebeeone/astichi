use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};
use rustpython_parser::ast;

use crate::handles::EngineHandle;
use crate::occurrence_store::{NativeAssemblyStateHandle, NativeEdgeHandle, NativeTemplateHandle};

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

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeMaterializationWorkspaceHandle>()?;
    m.add_function(wrap_pyfunction!(materialization_workspace_create, m)?)?;
    m.add_function(wrap_pyfunction!(materialization_workspace_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(
        materialization_workspace_resolve_locator,
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

fn replace_statement_at_path(
    module: &mut ast::ModModule,
    statement_path: &str,
    replacement: ast::Stmt,
) -> PyResult<()> {
    let segments = parse_ast_path(statement_path)?;
    replace_statement_in_body(&mut module.body, &segments, replacement)
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
