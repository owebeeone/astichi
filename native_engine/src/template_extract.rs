use std::collections::BTreeSet;

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyModule};
use rustpython_parser::ast;
use rustpython_parser::text_size::TextRange;

use crate::handles::EngineHandle;

const STRUCTURAL_SCHEMA: &str = "astichi.structural-inventory.v1";
const ARG_SUFFIX: &str = "__astichi_arg__";
const KEEP_SUFFIX: &str = "__astichi_keep__";
const PARAM_HOLE_SUFFIX: &str = "__astichi_param_hole__";
const ASSIGN_BIND_PREFIX: &str = "__astichi_assign__";
const DIRECTIVE_PLACEHOLDER_PREFIX: &str = "__astichi_ph_";
const DIRECTIVE_PLACEHOLDER_SUFFIX: &str = "__";
const DEFAULTED_BLOCK_FALLBACK_NAME: &str = "astichi_fallback";

#[derive(Clone)]
pub(crate) struct SourceMap {
    line_starts: Vec<usize>,
    import_names: BTreeSet<String>,
    export_names: BTreeSet<String>,
}

impl SourceMap {
    pub(crate) fn new(source: &str) -> Self {
        let mut line_starts = vec![0];
        for (idx, byte) in source.bytes().enumerate() {
            if byte == b'\n' {
                line_starts.push(idx + 1);
            }
        }
        Self {
            line_starts,
            import_names: BTreeSet::new(),
            export_names: BTreeSet::new(),
        }
    }

    fn for_module(source: &str, module: &ast::ModModule) -> Self {
        let mut source_map = Self::new(source);
        let marker_names = collect_direct_import_export_names(module);
        source_map.import_names = marker_names.import_names;
        source_map.export_names = marker_names.export_names;
        source_map
    }

    pub(crate) fn line(&self, range: TextRange) -> usize {
        let offset = range.start().to_u32() as usize;
        match self.line_starts.binary_search(&offset) {
            Ok(idx) => idx + 1,
            Err(idx) => idx,
        }
    }
}

#[derive(Clone)]
pub(crate) struct ExtractedRecord {
    pub(crate) ast_path: String,
    pub(crate) authored_summary: String,
    pub(crate) role_key: String,
    pub(crate) materialization_anchor: String,
    pub(crate) inventory_kind: String,
    pub(crate) resource_name: String,
    pub(crate) semantic_summary: String,
    pub(crate) surface_key: String,
    pub(crate) code_owner: Vec<String>,
}

struct RootBodyEntry<'a> {
    stmt: &'a ast::Stmt,
    path: String,
}

struct DirectImportExportNames {
    import_names: BTreeSet<String>,
    export_names: BTreeSet<String>,
}

#[derive(Clone, Copy)]
enum ExprRecordContext {
    Statement,
    Expression,
    CallArgument,
    PositionalVariadic,
    NamedVariadic,
}

/// Shared native compile validation: parse plus authored-surface placement rules.
pub(crate) fn validate_compile_module(
    source: &str,
    filename: &str,
) -> PyResult<ast::ModModule> {
    reject_deferred_markers(source)?;
    let module = crate::parser_ir::parse_native_module(source, filename)?;
    let source_map = SourceMap::new(source);
    validate_special_surface_placement(&module, &source_map)?;
    Ok(module)
}

#[pyfunction(name = "compile_validate_source")]
#[pyo3(signature = (source, filename = None))]
fn compile_validate_source_py(source: String, filename: Option<String>) -> PyResult<()> {
    let filename = filename.unwrap_or_else(|| "<astichi>".to_string());
    let module = validate_compile_module(&source, &filename)?;
    validate_authored_no_astichi_insert(&module, &SourceMap::new(&source))?;
    Ok(())
}

#[pyfunction]
#[pyo3(signature = (engine, source, filename = None, line_number = 1))]
fn extract_template_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    source: String,
    filename: Option<String>,
    line_number: u32,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    let surface_bundle = engine
        .surface_bundle()
        .ok_or_else(|| crate::errors::schema_error("surface bundle has not been registered"))?;

    let filename = filename.unwrap_or_else(|| "<astichi-native>".to_string());
    let module = validate_compile_module(&source, &filename)?;
    let records = extract_template_records(&source, &module, line_number)?;

    let source_summary = "compile line=".to_string()
        + &line_number.to_string()
        + " records="
        + &records.len().to_string();
    let template_key = template_key_from_source(&source);

    structural_snapshot(
        py,
        surface_bundle.snapshot(py)?,
        &template_key,
        &source_summary,
        &records,
    )
}

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_template_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(compile_validate_source_py, m)?)?;
    Ok(())
}

fn reject_deferred_markers(source: &str) -> PyResult<()> {
    validate_deferred_marker_text(source)?;
    Ok(())
}

fn validate_deferred_marker_text(_source: &str) -> PyResult<()> {
    Ok(())
}

pub(crate) fn extract_template_records(
    source: &str,
    module: &ast::ModModule,
    line_number: u32,
) -> PyResult<Vec<ExtractedRecord>> {
    let mut records = extract_records(source, module)?;
    if should_include_block_production(module) {
        let source_map = SourceMap::new(source);
        records.push(block_production_record(block_production_line_number(
            module,
            &source_map,
            line_number,
        )));
    }
    Ok(records)
}

fn extract_records(source: &str, module: &ast::ModModule) -> PyResult<Vec<ExtractedRecord>> {
    let source_map = SourceMap::for_module(source, module);
    let mut records = Vec::new();
    let entries = root_body_entries(module);
    for entry in &entries {
        stmt_records(entry.stmt, &entry.path, &source_map, &[], &mut records)?;
    }
    if let Some(record) = root_funcargs_production_record(&entries, &source_map) {
        records.push(record);
    }
    if let Some(record) = implicit_expression_production_record(&entries, &source_map) {
        records.push(record);
    }
    Ok(records)
}

fn root_body_entries(module: &ast::ModModule) -> Vec<RootBodyEntry<'_>> {
    module
        .body
        .iter()
        .enumerate()
        .map(|(index, stmt)| RootBodyEntry {
            stmt,
            path: format!("body[{index}]"),
        })
        .collect()
}

fn collect_direct_import_export_names(module: &ast::ModModule) -> DirectImportExportNames {
    let mut names = DirectImportExportNames {
        import_names: BTreeSet::new(),
        export_names: BTreeSet::new(),
    };
    for stmt in &module.body {
        collect_direct_import_export_names_stmt(stmt, &mut names);
    }
    names
}

fn collect_direct_import_export_names_stmt(stmt: &ast::Stmt, names: &mut DirectImportExportNames) {
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            for decorator in &node.decorator_list {
                collect_direct_import_export_names_expr(decorator, names);
            }
            for stmt in &node.body {
                collect_direct_import_export_names_stmt(stmt, names);
            }
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            for decorator in &node.decorator_list {
                collect_direct_import_export_names_expr(decorator, names);
            }
            for stmt in &node.body {
                collect_direct_import_export_names_stmt(stmt, names);
            }
        }
        ast::Stmt::ClassDef(node) => {
            for base in &node.bases {
                collect_direct_import_export_names_expr(base, names);
            }
            for keyword in &node.keywords {
                collect_direct_import_export_names_expr(&keyword.value, names);
            }
            for decorator in &node.decorator_list {
                collect_direct_import_export_names_expr(decorator, names);
            }
            for stmt in &node.body {
                collect_direct_import_export_names_stmt(stmt, names);
            }
        }
        ast::Stmt::Expr(node) => collect_direct_import_export_names_expr(&node.value, names),
        ast::Stmt::Assign(node) => {
            for target in &node.targets {
                collect_direct_import_export_names_expr(target, names);
            }
            collect_direct_import_export_names_expr(&node.value, names);
        }
        ast::Stmt::AnnAssign(node) => {
            collect_direct_import_export_names_expr(&node.target, names);
            collect_direct_import_export_names_expr(&node.annotation, names);
            if let Some(value) = node.value.as_ref() {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Stmt::AugAssign(node) => {
            collect_direct_import_export_names_expr(&node.target, names);
            collect_direct_import_export_names_expr(&node.value, names);
        }
        ast::Stmt::Return(node) => {
            if let Some(value) = node.value.as_ref() {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Stmt::With(node) => {
            for item in &node.items {
                collect_direct_import_export_names_expr(&item.context_expr, names);
                if let Some(value) = item.optional_vars.as_ref() {
                    collect_direct_import_export_names_expr(value, names);
                }
            }
            for stmt in &node.body {
                collect_direct_import_export_names_stmt(stmt, names);
            }
        }
        ast::Stmt::If(node) => {
            collect_direct_import_export_names_expr(&node.test, names);
            for stmt in &node.body {
                collect_direct_import_export_names_stmt(stmt, names);
            }
            for stmt in &node.orelse {
                collect_direct_import_export_names_stmt(stmt, names);
            }
        }
        _ => {}
    }
}

fn collect_direct_import_export_names_expr(expr: &ast::Expr, names: &mut DirectImportExportNames) {
    match expr {
        ast::Expr::Call(node) => {
            if let Some(marker_name @ ("astichi_import" | "astichi_export")) = call_name(&node.func)
            {
                if let Some(resource_name) = first_name_arg_unchecked(node) {
                    if marker_name == "astichi_import" {
                        names.import_names.insert(resource_name);
                    } else {
                        names.export_names.insert(resource_name);
                    }
                }
            }
            collect_direct_import_export_names_expr(&node.func, names);
            for arg in &node.args {
                collect_direct_import_export_names_expr(arg, names);
            }
            for keyword in &node.keywords {
                collect_direct_import_export_names_expr(&keyword.value, names);
            }
        }
        ast::Expr::BoolOp(node) => {
            for value in &node.values {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::NamedExpr(node) => {
            collect_direct_import_export_names_expr(&node.target, names);
            collect_direct_import_export_names_expr(&node.value, names);
        }
        ast::Expr::BinOp(node) => {
            collect_direct_import_export_names_expr(&node.left, names);
            collect_direct_import_export_names_expr(&node.right, names);
        }
        ast::Expr::UnaryOp(node) => collect_direct_import_export_names_expr(&node.operand, names),
        ast::Expr::Lambda(node) => collect_direct_import_export_names_expr(&node.body, names),
        ast::Expr::IfExp(node) => {
            collect_direct_import_export_names_expr(&node.test, names);
            collect_direct_import_export_names_expr(&node.body, names);
            collect_direct_import_export_names_expr(&node.orelse, names);
        }
        ast::Expr::Dict(node) => {
            for key in node.keys.iter().flatten() {
                collect_direct_import_export_names_expr(key, names);
            }
            for value in &node.values {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::Set(node) => {
            for value in &node.elts {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::List(node) => {
            for value in &node.elts {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::Tuple(node) => {
            for value in &node.elts {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::Attribute(node) => collect_direct_import_export_names_expr(&node.value, names),
        ast::Expr::Subscript(node) => {
            collect_direct_import_export_names_expr(&node.value, names);
            collect_direct_import_export_names_expr(&node.slice, names);
        }
        ast::Expr::Starred(node) => collect_direct_import_export_names_expr(&node.value, names),
        ast::Expr::Compare(node) => {
            collect_direct_import_export_names_expr(&node.left, names);
            for value in &node.comparators {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::FormattedValue(node) => {
            collect_direct_import_export_names_expr(&node.value, names);
            if let Some(value) = node.format_spec.as_ref() {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::JoinedStr(node) => {
            for value in &node.values {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::Slice(node) => {
            if let Some(value) = node.lower.as_ref() {
                collect_direct_import_export_names_expr(value, names);
            }
            if let Some(value) = node.upper.as_ref() {
                collect_direct_import_export_names_expr(value, names);
            }
            if let Some(value) = node.step.as_ref() {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::ListComp(node) => {
            collect_direct_import_export_names_expr(&node.elt, names);
            collect_direct_import_export_names_comprehensions(&node.generators, names);
        }
        ast::Expr::SetComp(node) => {
            collect_direct_import_export_names_expr(&node.elt, names);
            collect_direct_import_export_names_comprehensions(&node.generators, names);
        }
        ast::Expr::DictComp(node) => {
            collect_direct_import_export_names_expr(&node.key, names);
            collect_direct_import_export_names_expr(&node.value, names);
            collect_direct_import_export_names_comprehensions(&node.generators, names);
        }
        ast::Expr::GeneratorExp(node) => {
            collect_direct_import_export_names_expr(&node.elt, names);
            collect_direct_import_export_names_comprehensions(&node.generators, names);
        }
        ast::Expr::Await(node) => collect_direct_import_export_names_expr(&node.value, names),
        ast::Expr::Yield(node) => {
            if let Some(value) = node.value.as_ref() {
                collect_direct_import_export_names_expr(value, names);
            }
        }
        ast::Expr::YieldFrom(node) => collect_direct_import_export_names_expr(&node.value, names),
        ast::Expr::Constant(_) | ast::Expr::Name(_) => {}
    }
}

fn collect_direct_import_export_names_comprehensions(
    comprehensions: &[ast::Comprehension],
    names: &mut DirectImportExportNames,
) {
    for comprehension in comprehensions {
        collect_direct_import_export_names_expr(&comprehension.target, names);
        collect_direct_import_export_names_expr(&comprehension.iter, names);
        for condition in &comprehension.ifs {
            collect_direct_import_export_names_expr(condition, names);
        }
    }
}

fn root_funcargs_production_record(
    entries: &[RootBodyEntry<'_>],
    source_map: &SourceMap,
) -> Option<ExtractedRecord> {
    let (entry, stmt) = single_payload_expression_after_boundary_prefix(entries)?;
    if !is_call_named(&stmt.value, "astichi_funcargs") {
        return None;
    }
    let path = format!("{}/value", entry.path);
    Some(record(
        &path,
        &authored_summary("__funcargs__", source_map.line(stmt.range)),
        "production.funcargs",
        "copy-call-arguments",
        "production.funcargs",
        "__funcargs__",
        "astichi.surface.funcargs.production",
    ))
}

fn implicit_expression_production_record(
    entries: &[RootBodyEntry<'_>],
    source_map: &SourceMap,
) -> Option<ExtractedRecord> {
    let (entry, stmt) = single_payload_expression_after_boundary_prefix(entries)?;
    if is_call_named(&stmt.value, "astichi_insert")
        || is_call_named(&stmt.value, "astichi_funcargs")
    {
        return None;
    }
    let path = format!("{}/value", entry.path);
    let line_number = source_map.line(stmt.range);
    Some(expression_production_record(&path, line_number))
}

fn single_payload_expression_after_boundary_prefix<'a>(
    entries: &'a [RootBodyEntry<'a>],
) -> Option<(&'a RootBodyEntry<'a>, &'a ast::StmtExpr)> {
    let entry = single_payload_statement_after_boundary_prefix(entries)?;
    let ast::Stmt::Expr(stmt) = entry.stmt else {
        return None;
    };
    Some((entry, stmt))
}

fn single_payload_statement_after_boundary_prefix<'a>(
    entries: &'a [RootBodyEntry<'a>],
) -> Option<&'a RootBodyEntry<'a>> {
    let mut payload: Option<&RootBodyEntry<'_>> = None;
    for entry in entries {
        if is_boundary_prefix_statement(entry.stmt) {
            continue;
        }
        if payload.is_some() {
            return None;
        }
        payload = Some(entry);
    }
    payload
}

fn first_non_prefix_entry<'a>(entries: &'a [RootBodyEntry<'a>]) -> Option<&'a RootBodyEntry<'a>> {
    entries
        .iter()
        .find(|entry| !is_boundary_prefix_statement(entry.stmt))
}

fn is_boundary_prefix_statement(stmt: &ast::Stmt) -> bool {
    let ast::Stmt::Expr(expr_stmt) = stmt else {
        return false;
    };
    match expr_stmt.value.as_ref() {
        ast::Expr::Call(node) => matches!(
            call_name(&node.func),
            Some("astichi_keep" | "astichi_export" | "astichi_import" | "astichi_pyimport")
        ),
        _ => false,
    }
}

fn validate_authored_no_astichi_insert(
    module: &ast::ModModule,
    source_map: &SourceMap,
) -> PyResult<()> {
    for stmt in &module.body {
        validate_stmt_no_authored_insert(stmt, source_map)?;
    }
    Ok(())
}

fn validate_stmt_no_authored_insert(stmt: &ast::Stmt, source_map: &SourceMap) -> PyResult<()> {
    if let ast::Stmt::Expr(expr_stmt) = stmt {
        if expr_tree_contains_insert(&expr_stmt.value) {
            let line = source_map.line(expr_stmt.range);
            return Err(crate::errors::schema_error(&format!(
                "astichi_insert(...) is internal emitted-source metadata and cannot be authored directly at line {line}"
            )));
        }
    }
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            for child in &node.body {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            for child in &node.body {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
        }
        ast::Stmt::ClassDef(node) => {
            for child in &node.body {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
        }
        ast::Stmt::With(node) => {
            for child in &node.body {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
        }
        ast::Stmt::If(node) => {
            for child in &node.body {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
            for child in &node.orelse {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
        }
        ast::Stmt::Try(node) => {
            for child in &node.body {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
            for child in &node.orelse {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
            for child in &node.finalbody {
                validate_stmt_no_authored_insert(child, source_map)?;
            }
            for handler in &node.handlers {
                if let ast::ExceptHandler::ExceptHandler(inner) = handler {
                    for child in &inner.body {
                        validate_stmt_no_authored_insert(child, source_map)?;
                    }
                }
            }
        }
        _ => {}
    }
    Ok(())
}

fn expr_tree_contains_insert(expr: &ast::Expr) -> bool {
    if is_call_named(expr, "astichi_insert") {
        return true;
    }
    match expr {
        ast::Expr::Call(node) => {
            expr_tree_contains_insert(&node.func)
                || node.args.iter().any(expr_tree_contains_insert)
                || node
                    .keywords
                    .iter()
                    .any(|keyword| expr_tree_contains_insert(&keyword.value))
        }
        ast::Expr::BinOp(node) => {
            expr_tree_contains_insert(&node.left) || expr_tree_contains_insert(&node.right)
        }
        ast::Expr::UnaryOp(node) => expr_tree_contains_insert(&node.operand),
        ast::Expr::BoolOp(node) => node.values.iter().any(expr_tree_contains_insert),
        ast::Expr::IfExp(node) => {
            expr_tree_contains_insert(&node.test)
                || expr_tree_contains_insert(&node.body)
                || expr_tree_contains_insert(&node.orelse)
        }
        ast::Expr::Dict(node) => {
            node.keys
                .iter()
                .filter_map(|key| key.as_ref())
                .any(expr_tree_contains_insert)
                || node.values.iter().any(expr_tree_contains_insert)
        }
        ast::Expr::List(node) => node.elts.iter().any(expr_tree_contains_insert),
        ast::Expr::Tuple(node) => node.elts.iter().any(expr_tree_contains_insert),
        ast::Expr::Set(node) => node.elts.iter().any(expr_tree_contains_insert),
        ast::Expr::ListComp(node) => {
            expr_tree_contains_insert(&node.elt)
                || node.generators.iter().any(comprehension_contains_insert)
        }
        ast::Expr::SetComp(node) => {
            expr_tree_contains_insert(&node.elt)
                || node.generators.iter().any(comprehension_contains_insert)
        }
        ast::Expr::DictComp(node) => {
            expr_tree_contains_insert(&node.key)
                || expr_tree_contains_insert(&node.value)
                || node.generators.iter().any(comprehension_contains_insert)
        }
        ast::Expr::GeneratorExp(node) => {
            expr_tree_contains_insert(&node.elt)
                || node.generators.iter().any(comprehension_contains_insert)
        }
        ast::Expr::Attribute(node) => expr_tree_contains_insert(&node.value),
        ast::Expr::Subscript(node) => {
            expr_tree_contains_insert(&node.value) || expr_tree_contains_insert(&node.slice)
        }
        ast::Expr::Starred(node) => expr_tree_contains_insert(&node.value),
        ast::Expr::NamedExpr(node) => {
            expr_tree_contains_insert(&node.target) || expr_tree_contains_insert(&node.value)
        }
        ast::Expr::Await(node) => expr_tree_contains_insert(&node.value),
        _ => false,
    }
}

fn comprehension_contains_insert(comprehension: &ast::Comprehension) -> bool {
    expr_tree_contains_insert(&comprehension.target)
        || expr_tree_contains_insert(&comprehension.iter)
        || comprehension.ifs.iter().any(expr_tree_contains_insert)
}

fn validate_special_surface_placement(
    module: &ast::ModModule,
    source_map: &SourceMap,
) -> PyResult<()> {
    validate_pyimport_prefix(&module.body, source_map)?;
    validate_elif_positions(&module.body, source_map)
}

fn validate_pyimport_prefix(body: &[ast::Stmt], source_map: &SourceMap) -> PyResult<()> {
    let mut prefix_open = true;
    for stmt in body {
        if is_pyimport_statement(stmt) {
            if !prefix_open {
                return Err(crate::errors::schema_error(&format!(
                    "astichi_pyimport(...) at line {} must appear in the contiguous top-of-Astichi-scope prefix",
                    statement_line(stmt, source_map)
                )));
            }
        } else if !is_pyimport_prefix_statement(stmt) && !is_python_module_prefix_statement(stmt) {
            prefix_open = false;
        }
        match stmt {
            ast::Stmt::FunctionDef(node) => validate_pyimport_prefix(&node.body, source_map)?,
            ast::Stmt::AsyncFunctionDef(node) => validate_pyimport_prefix(&node.body, source_map)?,
            ast::Stmt::ClassDef(node) => validate_pyimport_prefix(&node.body, source_map)?,
            ast::Stmt::With(node) => validate_pyimport_prefix(&node.body, source_map)?,
            ast::Stmt::If(node) => {
                validate_pyimport_prefix(&node.body, source_map)?;
                validate_pyimport_prefix(&node.orelse, source_map)?;
            }
            ast::Stmt::Try(node) => {
                validate_pyimport_prefix(&node.body, source_map)?;
                validate_pyimport_prefix(&node.orelse, source_map)?;
                validate_pyimport_prefix(&node.finalbody, source_map)?;
                for handler in &node.handlers {
                    validate_pyimport_prefix_in_except_handler(handler, source_map)?;
                }
            }
            _ => {}
        }
    }
    Ok(())
}

fn validate_pyimport_prefix_in_except_handler(
    handler: &ast::ExceptHandler,
    source_map: &SourceMap,
) -> PyResult<()> {
    match handler {
        ast::ExceptHandler::ExceptHandler(node) => validate_pyimport_prefix(&node.body, source_map),
    }
}

fn is_pyimport_statement(stmt: &ast::Stmt) -> bool {
    let ast::Stmt::Expr(expr_stmt) = stmt else {
        return false;
    };
    is_call_named(&expr_stmt.value, "astichi_pyimport")
}

fn is_pyimport_prefix_statement(stmt: &ast::Stmt) -> bool {
    if is_boundary_prefix_statement(stmt) {
        return true;
    }
    let ast::Stmt::Expr(expr_stmt) = stmt else {
        return false;
    };
    is_call_named(&expr_stmt.value, "astichi_bind_external")
        || is_call_named(&expr_stmt.value, "astichi_comment")
}

fn is_python_module_prefix_statement(stmt: &ast::Stmt) -> bool {
    is_docstring_statement(stmt) || is_future_import_statement(stmt)
}

fn is_docstring_statement(stmt: &ast::Stmt) -> bool {
    let ast::Stmt::Expr(expr_stmt) = stmt else {
        return false;
    };
    match expr_stmt.value.as_ref() {
        ast::Expr::Constant(node) => matches!(node.value, ast::Constant::Str(_)),
        _ => false,
    }
}

fn is_future_import_statement(stmt: &ast::Stmt) -> bool {
    let ast::Stmt::ImportFrom(node) = stmt else {
        return false;
    };
    node.module.as_ref().map(|module| module.as_str()) == Some("__future__")
}

fn validate_elif_positions(body: &[ast::Stmt], source_map: &SourceMap) -> PyResult<()> {
    for stmt in body {
        validate_elif_statement(stmt, false, source_map)?;
    }
    Ok(())
}

fn validate_elif_statement(
    stmt: &ast::Stmt,
    valid_elif_position: bool,
    source_map: &SourceMap,
) -> PyResult<()> {
    let ast::Stmt::If(node) = stmt else {
        match stmt {
            ast::Stmt::FunctionDef(node) => validate_elif_positions(&node.body, source_map)?,
            ast::Stmt::AsyncFunctionDef(node) => validate_elif_positions(&node.body, source_map)?,
            ast::Stmt::ClassDef(node) => validate_elif_positions(&node.body, source_map)?,
            ast::Stmt::With(node) => validate_elif_positions(&node.body, source_map)?,
            ast::Stmt::Try(node) => {
                validate_elif_positions(&node.body, source_map)?;
                validate_elif_positions(&node.orelse, source_map)?;
                validate_elif_positions(&node.finalbody, source_map)?;
                for handler in &node.handlers {
                    validate_elif_positions_in_except_handler(handler, source_map)?;
                }
            }
            _ => {}
        }
        return Ok(());
    };
    if is_call_named(&node.test, "astichi_elif") {
        if !valid_elif_position {
            return Err(crate::errors::schema_error(&format!(
                "astichi_elif(...) at line {} is valid only in real elif position",
                source_map.line(node.range)
            )));
        }
        validate_elif_empty_body(&node.body, source_map)?;
    }
    for child in &node.body {
        validate_elif_statement(child, false, source_map)?;
    }
    for (index, child) in node.orelse.iter().enumerate() {
        validate_elif_statement(child, index == 0, source_map)?;
    }
    Ok(())
}

fn validate_elif_positions_in_except_handler(
    handler: &ast::ExceptHandler,
    source_map: &SourceMap,
) -> PyResult<()> {
    match handler {
        ast::ExceptHandler::ExceptHandler(node) => validate_elif_positions(&node.body, source_map),
    }
}

fn validate_elif_empty_body(body: &[ast::Stmt], source_map: &SourceMap) -> PyResult<()> {
    for stmt in body {
        if matches!(stmt, ast::Stmt::Pass(_)) {
            continue;
        }
        if is_comment_statement(stmt) {
            continue;
        }
        return Err(crate::errors::schema_error(&format!(
            "astichi_elif marker body at line {} must be empty-equivalent",
            statement_line(stmt, source_map)
        )));
    }
    Ok(())
}

fn is_comment_statement(stmt: &ast::Stmt) -> bool {
    let ast::Stmt::Expr(expr_stmt) = stmt else {
        return false;
    };
    is_call_named(&expr_stmt.value, "astichi_comment")
}

fn statement_line(stmt: &ast::Stmt, source_map: &SourceMap) -> usize {
    match stmt {
        ast::Stmt::FunctionDef(node) => source_map.line(node.range),
        ast::Stmt::AsyncFunctionDef(node) => source_map.line(node.range),
        ast::Stmt::ClassDef(node) => source_map.line(node.range),
        ast::Stmt::Expr(node) => source_map.line(node.range),
        ast::Stmt::Assign(node) => source_map.line(node.range),
        ast::Stmt::AnnAssign(node) => source_map.line(node.range),
        ast::Stmt::Return(node) => source_map.line(node.range),
        ast::Stmt::Import(node) => source_map.line(node.range),
        ast::Stmt::ImportFrom(node) => source_map.line(node.range),
        ast::Stmt::With(node) => source_map.line(node.range),
        ast::Stmt::If(node) => source_map.line(node.range),
        ast::Stmt::Try(node) => source_map.line(node.range),
        _ => 1,
    }
}

fn should_include_block_production(module: &ast::ModModule) -> bool {
    let entries = root_body_entries(module);
    if let Some(entry) = single_payload_statement_after_boundary_prefix(&entries) {
        match entry.stmt {
            ast::Stmt::Expr(stmt) if is_call_named(&stmt.value, "astichi_funcargs") => {
                return false;
            }
            ast::Stmt::FunctionDef(node) if node.name.as_str() == "astichi_params" => {
                return false;
            }
            ast::Stmt::AsyncFunctionDef(node) if node.name.as_str() == "astichi_params" => {
                return false;
            }
            _ => {}
        }
    }
    true
}

fn block_production_line_number(
    module: &ast::ModModule,
    source_map: &SourceMap,
    fallback: u32,
) -> usize {
    if let Some(line_number) = root_shell_block_line_number(module, source_map) {
        return origin_adjusted_line(line_number, fallback);
    }
    let entries = root_body_entries(module);
    let Some(entry) = first_non_prefix_entry(&entries).or_else(|| entries.first()) else {
        return fallback as usize;
    };
    origin_adjusted_line(statement_line(entry.stmt, source_map), fallback)
}

fn origin_adjusted_line(source_line: usize, fallback: u32) -> usize {
    if source_line == 1 {
        fallback as usize
    } else {
        source_line
    }
}

fn root_shell_block_line_number(module: &ast::ModModule, source_map: &SourceMap) -> Option<usize> {
    let mut matched_body: Option<&[ast::Stmt]> = None;
    for stmt in &module.body {
        let ast::Stmt::FunctionDef(node) = stmt else {
            continue;
        };
        if !node.name.as_str().starts_with("__astichi_root__") {
            continue;
        }
        if matched_body.is_some() {
            return None;
        }
        matched_body = Some(&node.body);
    }
    let body = matched_body?;
    let stmt = body
        .iter()
        .find(|stmt| !is_boundary_prefix_statement(stmt))
        .or_else(|| body.first())?;
    Some(statement_line(stmt, source_map))
}

fn child_owner(owner: &[String], name: &str) -> Vec<String> {
    let mut child = owner.to_vec();
    child.push(strip_known_suffix(name));
    child
}

fn stmt_records(
    stmt: &ast::Stmt,
    path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    match stmt {
        ast::Stmt::Expr(node) => {
            expr_records(
                &node.value,
                &(path.to_string() + "/value"),
                source_map,
                ExprRecordContext::Statement,
                owner,
                records,
            )?;
            Ok(())
        }
        ast::Stmt::Assign(node) => {
            for (index, target) in node.targets.iter().enumerate() {
                expr_records(
                    target,
                    &format!("{path}/targets[{index}]"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            expr_records(
                &node.value,
                &(path.to_string() + "/value"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )
        }
        ast::Stmt::AnnAssign(node) => {
            expr_records(
                &node.target,
                &(path.to_string() + "/target"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.annotation,
                &(path.to_string() + "/annotation"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            if let Some(value) = node.value.as_ref() {
                expr_records(
                    value,
                    &(path.to_string() + "/value"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::AugAssign(node) => {
            expr_records(
                &node.target,
                &(path.to_string() + "/target"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.value,
                &(path.to_string() + "/value"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )
        }
        ast::Stmt::Delete(node) => {
            for (index, target) in node.targets.iter().enumerate() {
                expr_records(
                    target,
                    &format!("{path}/targets[{index}]"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Return(node) => {
            if let Some(value) = node.value.as_ref() {
                expr_records(
                    value,
                    &(path.to_string() + "/value"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::For(node) => {
            expr_records(
                &node.target,
                &(path.to_string() + "/target"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.iter,
                &(path.to_string() + "/iter"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            for (index, stmt) in node.orelse.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/orelse[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::While(node) => {
            expr_records(
                &node.test,
                &(path.to_string() + "/test"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            for (index, stmt) in node.orelse.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/orelse[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::With(node) => {
            defaulted_block_hole_record(node, path, source_map, owner, records)?;
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::If(node) => {
            if is_call_named(&node.test, "astichi_elif") {
                let ast::Expr::Call(call) = node.test.as_ref() else {
                    unreachable!("is_call_named already matched Call")
                };
                let resource_name = first_name_arg(call, "astichi_elif")?;
                records.push(record_with_owner(
                    &(path.to_string() + "/test"),
                    &authored_summary(&resource_name, source_map.line(call.range)),
                    "hole.elif",
                    "append-clause",
                    "hole.elif",
                    &resource_name,
                    "astichi.surface.elif.target",
                    owner.to_vec(),
                ));
            } else {
                expr_records(
                    &node.test,
                    &(path.to_string() + "/test"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            for (index, stmt) in node.orelse.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/orelse[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Try(node) => {
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            for (index, handler) in node.handlers.iter().enumerate() {
                except_handler_records(
                    handler,
                    &format!("{path}/handlers[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            for (index, stmt) in node.orelse.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/orelse[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            for (index, stmt) in node.finalbody.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/finalbody[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Assert(node) => {
            expr_records(
                &node.test,
                &(path.to_string() + "/test"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            if let Some(msg) = node.msg.as_ref() {
                expr_records(
                    msg,
                    &(path.to_string() + "/msg"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Raise(node) => {
            if let Some(exc) = node.exc.as_ref() {
                expr_records(
                    exc,
                    &(path.to_string() + "/exc"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            if let Some(cause) = node.cause.as_ref() {
                expr_records(
                    cause,
                    &(path.to_string() + "/cause"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::FunctionDef(node) => {
            let function_owner = child_owner(owner, node.name.as_str());
            if node.name.as_str() == "astichi_elif" {
                records.push(record(
                    path,
                    &authored_summary("astichi_elif", source_map.line(node.range)),
                    "production.elif",
                    "copy-clause",
                    "production.elif",
                    "astichi_elif",
                    "astichi.surface.elif.production",
                ));
            } else if node.name.as_str() == "astichi_params" {
                records.push(record(
                    path,
                    &authored_summary("astichi_params", source_map.line(node.range)),
                    "production.supply",
                    "copy-parameters",
                    "production.supply",
                    "astichi_params",
                    "astichi.surface.parameter.production",
                ));
                function_argument_suffix_records(
                    &node.args,
                    path,
                    &function_owner,
                    source_map,
                    records,
                )?;
                return Ok(());
            } else if let Some(resource_name) = strip_arg_suffix(node.name.as_str()) {
                records.push(identifier_demand_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            decorator_records(
                &node.decorator_list,
                path,
                source_map,
                &function_owner,
                records,
            )?;
            function_argument_suffix_records(
                &node.args,
                path,
                &function_owner,
                source_map,
                records,
            )?;
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    &function_owner,
                    records,
                )?;
            }
            decorator_expr_records(
                &node.decorator_list,
                path,
                source_map,
                &function_owner,
                records,
            )?;
            Ok(())
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            let function_owner = child_owner(owner, node.name.as_str());
            if node.name.as_str() == "astichi_elif" {
                records.push(record(
                    path,
                    &authored_summary("astichi_elif", source_map.line(node.range)),
                    "production.elif",
                    "copy-clause",
                    "production.elif",
                    "astichi_elif",
                    "astichi.surface.elif.production",
                ));
            } else if node.name.as_str() == "astichi_params" {
                records.push(record(
                    path,
                    &authored_summary("astichi_params", source_map.line(node.range)),
                    "production.supply",
                    "copy-parameters",
                    "production.supply",
                    "astichi_params",
                    "astichi.surface.parameter.production",
                ));
                function_argument_suffix_records(
                    &node.args,
                    path,
                    &function_owner,
                    source_map,
                    records,
                )?;
                return Ok(());
            } else if let Some(resource_name) = strip_arg_suffix(node.name.as_str()) {
                records.push(identifier_demand_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            decorator_records(
                &node.decorator_list,
                path,
                source_map,
                &function_owner,
                records,
            )?;
            function_argument_suffix_records(
                &node.args,
                path,
                &function_owner,
                source_map,
                records,
            )?;
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    &function_owner,
                    records,
                )?;
            }
            decorator_expr_records(
                &node.decorator_list,
                path,
                source_map,
                &function_owner,
                records,
            )?;
            Ok(())
        }
        ast::Stmt::ClassDef(node) => {
            let class_owner = child_owner(owner, node.name.as_str());
            if let Some(resource_name) = strip_arg_suffix(node.name.as_str()) {
                records.push(identifier_demand_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            for (index, base) in node.bases.iter().enumerate() {
                expr_records(
                    base,
                    &format!("{path}/bases[{index}]"),
                    source_map,
                    ExprRecordContext::Expression,
                    &class_owner,
                    records,
                )?;
            }
            for (index, keyword) in node.keywords.iter().enumerate() {
                if let Some(arg) = keyword.arg.as_ref() {
                    if let Some(resource_name) = strip_arg_suffix(arg.as_str()) {
                        records.push(identifier_demand_record(
                            &format!("{path}/keywords[{index}]"),
                            &resource_name,
                            source_map.line(keyword.range),
                            class_owner.clone(),
                        ));
                    }
                }
                expr_records(
                    &keyword.value,
                    &format!("{path}/keywords[{index}]/value"),
                    source_map,
                    ExprRecordContext::Expression,
                    &class_owner,
                    records,
                )?;
            }
            decorator_records(
                &node.decorator_list,
                path,
                source_map,
                &class_owner,
                records,
            )?;
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    &class_owner,
                    records,
                )?;
            }
            decorator_expr_records(
                &node.decorator_list,
                path,
                source_map,
                &class_owner,
                records,
            )?;
            Ok(())
        }
        ast::Stmt::Import(node) => {
            for (index, alias) in node.names.iter().enumerate() {
                alias_suffix_records(
                    alias,
                    &format!("{path}/names[{index}]"),
                    source_map,
                    owner,
                    records,
                );
            }
            Ok(())
        }
        ast::Stmt::ImportFrom(node) => {
            if let Some(module) = node.module.as_ref() {
                if let Some(resource_name) = strip_arg_suffix(module.as_str()) {
                    records.push(identifier_demand_record(
                        path,
                        &resource_name,
                        source_map.line(node.range),
                        owner.to_vec(),
                    ));
                }
            }
            for (index, alias) in node.names.iter().enumerate() {
                alias_suffix_records(
                    alias,
                    &format!("{path}/names[{index}]"),
                    source_map,
                    owner,
                    records,
                );
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn except_handler_records(
    handler: &ast::ExceptHandler,
    path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    match handler {
        ast::ExceptHandler::ExceptHandler(node) => {
            if let Some(type_) = node.type_.as_ref() {
                expr_records(
                    type_,
                    &(path.to_string() + "/type"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
    }
}

fn expr_records(
    expr: &ast::Expr,
    path: &str,
    source_map: &SourceMap,
    context: ExprRecordContext,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    match expr {
        ast::Expr::Call(node) => {
            let name = marker_call_name(&node.func);
            let defer_attribute_ref_record = name == Some("astichi_ref")
                && matches!(node.func.as_ref(), ast::Expr::Attribute(_));
            if let Some(name) = name.filter(|_| !defer_attribute_ref_record) {
                direct_call_record(name, node, path, source_map, context, owner, records)?;
            }
            expr_records(
                &node.func,
                &(path.to_string() + "/func"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            if defer_attribute_ref_record {
                direct_call_record(
                    "astichi_ref",
                    node,
                    path,
                    source_map,
                    context,
                    owner,
                    records,
                )?;
            }
            for (index, arg) in node.args.iter().enumerate() {
                let arg_context = if matches!(arg, ast::Expr::Starred(_)) {
                    ExprRecordContext::PositionalVariadic
                } else {
                    ExprRecordContext::CallArgument
                };
                expr_records(
                    arg,
                    &format!("{path}/args[{index}]"),
                    source_map,
                    arg_context,
                    owner,
                    records,
                )?;
            }
            for (index, keyword) in node.keywords.iter().enumerate() {
                if let Some(arg) = keyword.arg.as_ref() {
                    if let Some(resource_name) = strip_arg_suffix(arg.as_str()) {
                        records.push(identifier_demand_record(
                            &format!("{path}/keywords[{index}]"),
                            &resource_name,
                            source_map.line(keyword.range),
                            owner.to_vec(),
                        ));
                    }
                }
                let keyword_context = if keyword.arg.is_none() {
                    ExprRecordContext::NamedVariadic
                } else {
                    ExprRecordContext::CallArgument
                };
                expr_records(
                    &keyword.value,
                    &format!("{path}/keywords[{index}]/value"),
                    source_map,
                    keyword_context,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Expr::Starred(node) => expr_records(
            &node.value,
            &(path.to_string() + "/value"),
            source_map,
            ExprRecordContext::PositionalVariadic,
            owner,
            records,
        ),
        ast::Expr::Name(node) => {
            if let Some(resource_name) = strip_arg_suffix(node.id.as_str()) {
                records.push(identifier_demand_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            Ok(())
        }
        ast::Expr::NamedExpr(node) => {
            expr_records(
                &node.target,
                &(path.to_string() + "/target"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.value,
                &(path.to_string() + "/value"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )
        }
        ast::Expr::BoolOp(node) => {
            for (index, value) in node.values.iter().enumerate() {
                expr_records(
                    value,
                    &format!("{path}/values[{index}]"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Expr::BinOp(node) => {
            expr_records(
                &node.left,
                &(path.to_string() + "/left"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.right,
                &(path.to_string() + "/right"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )
        }
        ast::Expr::UnaryOp(node) => expr_records(
            &node.operand,
            &(path.to_string() + "/operand"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        ),
        ast::Expr::Lambda(node) => {
            function_argument_suffix_records(&node.args, path, owner, source_map, records)?;
            expr_records(
                &node.body,
                &(path.to_string() + "/body"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )
        }
        ast::Expr::IfExp(node) => {
            expr_records(
                &node.test,
                &(path.to_string() + "/test"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.body,
                &(path.to_string() + "/body"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.orelse,
                &(path.to_string() + "/orelse"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )
        }
        ast::Expr::Dict(node) => {
            for (index, key) in node.keys.iter().enumerate() {
                if let Some(key) = key {
                    expr_records(
                        key,
                        &format!("{path}/keys[{index}]"),
                        source_map,
                        ExprRecordContext::Expression,
                        owner,
                        records,
                    )?;
                }
            }
            for (index, value) in node.values.iter().enumerate() {
                let value_context = if node.keys[index].is_none() {
                    ExprRecordContext::NamedVariadic
                } else {
                    ExprRecordContext::Expression
                };
                expr_records(
                    value,
                    &format!("{path}/values[{index}]"),
                    source_map,
                    value_context,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Expr::Set(node) => expr_sequence_records(&node.elts, path, source_map, owner, records),
        ast::Expr::List(node) => {
            expr_sequence_records(&node.elts, path, source_map, owner, records)
        }
        ast::Expr::Tuple(node) => {
            expr_sequence_records(&node.elts, path, source_map, owner, records)
        }
        ast::Expr::Compare(node) => {
            expr_records(
                &node.left,
                &(path.to_string() + "/left"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            for (index, value) in node.comparators.iter().enumerate() {
                expr_records(
                    value,
                    &format!("{path}/comparators[{index}]"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Expr::Attribute(node) => expr_records(
            &node.value,
            &(path.to_string() + "/value"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        ),
        ast::Expr::Subscript(node) => {
            expr_records(
                &node.value,
                &(path.to_string() + "/value"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.slice,
                &(path.to_string() + "/slice"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )
        }
        ast::Expr::Slice(node) => {
            if let Some(value) = node.lower.as_ref() {
                expr_records(
                    value,
                    &(path.to_string() + "/lower"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            if let Some(value) = node.upper.as_ref() {
                expr_records(
                    value,
                    &(path.to_string() + "/upper"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            if let Some(value) = node.step.as_ref() {
                expr_records(
                    value,
                    &(path.to_string() + "/step"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Expr::FormattedValue(node) => {
            expr_records(
                &node.value,
                &(path.to_string() + "/value"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            if let Some(value) = node.format_spec.as_ref() {
                expr_records(
                    value,
                    &(path.to_string() + "/format_spec"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Expr::JoinedStr(node) => {
            for (index, value) in node.values.iter().enumerate() {
                expr_records(
                    value,
                    &format!("{path}/values[{index}]"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Expr::ListComp(node) => {
            expr_records(
                &node.elt,
                &(path.to_string() + "/elt"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            comprehension_expr_records(&node.generators, path, source_map, owner, records)
        }
        ast::Expr::SetComp(node) => {
            expr_records(
                &node.elt,
                &(path.to_string() + "/elt"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            comprehension_expr_records(&node.generators, path, source_map, owner, records)
        }
        ast::Expr::DictComp(node) => {
            expr_records(
                &node.key,
                &(path.to_string() + "/key"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            expr_records(
                &node.value,
                &(path.to_string() + "/value"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            comprehension_expr_records(&node.generators, path, source_map, owner, records)
        }
        ast::Expr::GeneratorExp(node) => {
            expr_records(
                &node.elt,
                &(path.to_string() + "/elt"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            comprehension_expr_records(&node.generators, path, source_map, owner, records)
        }
        ast::Expr::Await(node) => expr_records(
            &node.value,
            &(path.to_string() + "/value"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        ),
        ast::Expr::Yield(node) => {
            if let Some(value) = node.value.as_ref() {
                expr_records(
                    value,
                    &(path.to_string() + "/value"),
                    source_map,
                    ExprRecordContext::Expression,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Expr::YieldFrom(node) => expr_records(
            &node.value,
            &(path.to_string() + "/value"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        ),
        ast::Expr::Constant(_) => Ok(()),
    }
}

fn comprehension_expr_records(
    comprehensions: &[ast::Comprehension],
    path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    for (index, comprehension) in comprehensions.iter().enumerate() {
        expr_records(
            &comprehension.target,
            &format!("{path}/generators[{index}]/target"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        )?;
        expr_records(
            &comprehension.iter,
            &format!("{path}/generators[{index}]/iter"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        )?;
        for (if_index, condition) in comprehension.ifs.iter().enumerate() {
            expr_records(
                condition,
                &format!("{path}/generators[{index}]/ifs[{if_index}]"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
        }
    }
    Ok(())
}

fn expr_sequence_records(
    values: &[ast::Expr],
    path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    for (index, value) in values.iter().enumerate() {
        expr_records(
            value,
            &format!("{path}/elts[{index}]"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        )?;
    }
    Ok(())
}

fn call_name(expr: &ast::Expr) -> Option<&str> {
    match expr {
        ast::Expr::Name(node) => Some(node.id.as_str()),
        _ => None,
    }
}

fn marker_call_name(expr: &ast::Expr) -> Option<&str> {
    match expr {
        ast::Expr::Name(node) => Some(node.id.as_str()),
        ast::Expr::Attribute(node) if node.attr.as_str() == "astichi_ref" => {
            Some(node.attr.as_str())
        }
        _ => None,
    }
}

fn is_call_named(expr: &ast::Expr, name: &str) -> bool {
    match expr {
        ast::Expr::Call(node) => marker_call_name(&node.func) == Some(name),
        _ => false,
    }
}

fn is_directive_call(expr: &ast::Expr) -> bool {
    match expr {
        ast::Expr::Call(node) => matches!(
            call_name(&node.func),
            Some("astichi_import" | "astichi_export")
        ),
        _ => false,
    }
}

fn directive_placeholder_index(name: &str) -> Option<usize> {
    if !name.starts_with(DIRECTIVE_PLACEHOLDER_PREFIX)
        || !name.ends_with(DIRECTIVE_PLACEHOLDER_SUFFIX)
    {
        return None;
    }
    let raw_index =
        &name[DIRECTIVE_PLACEHOLDER_PREFIX.len()..name.len() - DIRECTIVE_PLACEHOLDER_SUFFIX.len()];
    if raw_index.is_empty() || !raw_index.chars().all(|ch| ch.is_ascii_digit()) {
        return None;
    }
    if raw_index.len() > 1 && raw_index.starts_with('0') {
        return None;
    }
    raw_index.parse().ok()
}

fn is_assign_bind_identifier(name: &str) -> bool {
    name.starts_with(ASSIGN_BIND_PREFIX)
}

fn contains_directive_call(expr: &ast::Expr) -> bool {
    match expr {
        ast::Expr::Call(node) => {
            is_directive_call(expr)
                || contains_directive_call(&node.func)
                || node.args.iter().any(contains_directive_call)
                || node
                    .keywords
                    .iter()
                    .any(|keyword| contains_directive_call(&keyword.value))
        }
        ast::Expr::BoolOp(node) => node.values.iter().any(contains_directive_call),
        ast::Expr::NamedExpr(node) => {
            contains_directive_call(&node.target) || contains_directive_call(&node.value)
        }
        ast::Expr::BinOp(node) => {
            contains_directive_call(&node.left) || contains_directive_call(&node.right)
        }
        ast::Expr::UnaryOp(node) => contains_directive_call(&node.operand),
        ast::Expr::Lambda(node) => contains_directive_call(&node.body),
        ast::Expr::IfExp(node) => {
            contains_directive_call(&node.test)
                || contains_directive_call(&node.body)
                || contains_directive_call(&node.orelse)
        }
        ast::Expr::Dict(node) => {
            node.keys.iter().flatten().any(contains_directive_call)
                || node.values.iter().any(contains_directive_call)
        }
        ast::Expr::Set(node) => node.elts.iter().any(contains_directive_call),
        ast::Expr::ListComp(node) => {
            contains_directive_call(&node.elt)
                || node
                    .generators
                    .iter()
                    .any(comprehension_contains_directive_call)
        }
        ast::Expr::SetComp(node) => {
            contains_directive_call(&node.elt)
                || node
                    .generators
                    .iter()
                    .any(comprehension_contains_directive_call)
        }
        ast::Expr::DictComp(node) => {
            contains_directive_call(&node.key)
                || contains_directive_call(&node.value)
                || node
                    .generators
                    .iter()
                    .any(comprehension_contains_directive_call)
        }
        ast::Expr::GeneratorExp(node) => {
            contains_directive_call(&node.elt)
                || node
                    .generators
                    .iter()
                    .any(comprehension_contains_directive_call)
        }
        ast::Expr::Await(node) => contains_directive_call(&node.value),
        ast::Expr::Yield(node) => node
            .value
            .iter()
            .any(|value| contains_directive_call(value)),
        ast::Expr::YieldFrom(node) => contains_directive_call(&node.value),
        ast::Expr::Compare(node) => {
            contains_directive_call(&node.left)
                || node.comparators.iter().any(contains_directive_call)
        }
        ast::Expr::FormattedValue(node) => {
            contains_directive_call(&node.value)
                || node
                    .format_spec
                    .iter()
                    .any(|value| contains_directive_call(value))
        }
        ast::Expr::JoinedStr(node) => node.values.iter().any(contains_directive_call),
        ast::Expr::Attribute(node) => contains_directive_call(&node.value),
        ast::Expr::Subscript(node) => {
            contains_directive_call(&node.value) || contains_directive_call(&node.slice)
        }
        ast::Expr::Starred(node) => contains_directive_call(&node.value),
        ast::Expr::List(node) => node.elts.iter().any(contains_directive_call),
        ast::Expr::Tuple(node) => node.elts.iter().any(contains_directive_call),
        ast::Expr::Slice(node) => {
            node.lower
                .iter()
                .any(|value| contains_directive_call(value))
                || node
                    .upper
                    .iter()
                    .any(|value| contains_directive_call(value))
                || node.step.iter().any(|value| contains_directive_call(value))
        }
        ast::Expr::Constant(_) | ast::Expr::Name(_) => false,
    }
}

fn comprehension_contains_directive_call(comprehension: &ast::Comprehension) -> bool {
    contains_directive_call(&comprehension.target)
        || contains_directive_call(&comprehension.iter)
        || comprehension.ifs.iter().any(contains_directive_call)
}

fn validate_funcargs_call(node: &ast::ExprCall) -> PyResult<()> {
    let mut indexes = Vec::new();
    for arg in &node.args {
        if contains_directive_call(arg) {
            return Err(crate::errors::schema_error(
                "astichi_import(...) / astichi_export(...) are only valid as direct __astichi_ph_{N}__= carriers inside astichi_funcargs(...)",
            ));
        }
    }
    for keyword in &node.keywords {
        let Some(arg) = keyword.arg.as_ref().map(|arg| arg.as_str()) else {
            if contains_directive_call(&keyword.value) {
                return Err(crate::errors::schema_error(
                    "astichi_import(...) / astichi_export(...) are only valid as direct __astichi_ph_{N}__= carriers inside astichi_funcargs(...)",
                ));
            }
            continue;
        };
        if arg == "_" {
            return Err(crate::errors::schema_error(
                "keyword `_` is reserved inside astichi_funcargs(...); use __astichi_ph_{N}__=astichi_import/export(...) for payload-local directives",
            ));
        }
        if arg.starts_with(DIRECTIVE_PLACEHOLDER_PREFIX) {
            let Some(index) = directive_placeholder_index(arg) else {
                return Err(crate::errors::schema_error(
                    "astichi_funcargs directive placeholder names must match __astichi_ph_{N}__",
                ));
            };
            if !is_directive_call(&keyword.value) {
                return Err(crate::errors::schema_error(
                    "astichi_funcargs directive placeholders may only carry direct astichi_import(...) or astichi_export(...) calls",
                ));
            }
            indexes.push(index);
        } else if contains_directive_call(&keyword.value) {
            return Err(crate::errors::schema_error(
                "astichi_import(...) / astichi_export(...) are only valid as direct __astichi_ph_{N}__= carriers inside astichi_funcargs(...)",
            ));
        }
    }
    if indexes.iter().copied().ne(0..indexes.len()) {
        return Err(crate::errors::schema_error(
            "astichi_funcargs directive placeholders must be contiguous and ordered from __astichi_ph_0__",
        ));
    }
    Ok(())
}

fn function_argument_suffix_records(
    args: &ast::Arguments,
    path: &str,
    owner: &[String],
    source_map: &SourceMap,
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    let mut default_index = 0usize;
    for (index, arg) in args.posonlyargs.iter().enumerate() {
        arg_records(
            &arg.def,
            &format!("{path}/args/posonlyargs[{index}]"),
            source_map,
            owner,
            records,
        )?;
        if let Some(default) = arg.default.as_ref() {
            expr_records(
                default,
                &format!("{path}/args/defaults[{default_index}]"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            default_index += 1;
        }
    }
    for (index, arg) in args.args.iter().enumerate() {
        arg_records(
            &arg.def,
            &format!("{path}/args/args[{index}]"),
            source_map,
            owner,
            records,
        )?;
        if let Some(default) = arg.default.as_ref() {
            expr_records(
                default,
                &format!("{path}/args/defaults[{default_index}]"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
            default_index += 1;
        }
    }
    for (index, arg) in args.kwonlyargs.iter().enumerate() {
        arg_records(
            &arg.def,
            &format!("{path}/args/kwonlyargs[{index}]"),
            source_map,
            owner,
            records,
        )?;
        if let Some(default) = arg.default.as_ref() {
            expr_records(
                default,
                &format!("{path}/args/kw_defaults[{index}]"),
                source_map,
                ExprRecordContext::Expression,
                owner,
                records,
            )?;
        }
    }
    if let Some(arg) = args.vararg.as_ref() {
        arg_records(
            arg,
            &(path.to_string() + "/args/vararg"),
            source_map,
            owner,
            records,
        )?;
    }
    if let Some(arg) = args.kwarg.as_ref() {
        arg_records(
            arg,
            &(path.to_string() + "/args/kwarg"),
            source_map,
            owner,
            records,
        )?;
    }
    Ok(())
}

fn arg_records(
    arg: &ast::Arg,
    path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    arg_suffix_record(arg, path, source_map, owner.to_vec(), records);
    if let Some(annotation) = arg.annotation.as_ref() {
        expr_records(
            annotation,
            &(path.to_string() + "/annotation"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        )?;
    }
    Ok(())
}

fn arg_suffix_record(
    arg: &ast::Arg,
    path: &str,
    source_map: &SourceMap,
    owner: Vec<String>,
    records: &mut Vec<ExtractedRecord>,
) {
    if let Some(resource_name) = strip_param_hole_suffix(arg.arg.as_str()) {
        records.push(record_with_owner(
            path,
            &authored_summary(&resource_name, source_map.line(arg.range)),
            "hole.params",
            "splice-parameters",
            "hole.params",
            &resource_name,
            "astichi.surface.parameter.hole",
            owner,
        ));
    } else if let Some(resource_name) = strip_arg_suffix(arg.arg.as_str()) {
        records.push(identifier_demand_record(
            path,
            &resource_name,
            source_map.line(arg.range),
            owner,
        ));
    }
}

fn alias_suffix_records(
    alias: &ast::Alias,
    path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) {
    if let Some(resource_name) = strip_arg_suffix(alias.name.as_str()) {
        records.push(identifier_demand_record(
            path,
            &resource_name,
            source_map.line(alias.range),
            owner.to_vec(),
        ));
    }
    if let Some(asname) = alias.asname.as_ref() {
        if let Some(resource_name) = strip_arg_suffix(asname.as_str()) {
            records.push(identifier_demand_record(
                path,
                &resource_name,
                source_map.line(alias.range),
                owner.to_vec(),
            ));
        }
    }
}

fn defaulted_block_hole_record(
    node: &ast::StmtWith,
    path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    let Some(item) = node.items.first() else {
        return Ok(());
    };
    let ast::Expr::Call(call) = &item.context_expr else {
        return Ok(());
    };
    if call_name(&call.func) != Some("astichi_hole") {
        return Ok(());
    }
    let Some(optional_vars) = item.optional_vars.as_ref() else {
        return Err(crate::errors::schema_error(
            "defaulted block holes require `as astichi_fallback`",
        ));
    };
    if !matches!(
        optional_vars.as_ref(),
        ast::Expr::Name(name) if name.id.as_str() == DEFAULTED_BLOCK_FALLBACK_NAME
    ) {
        return Err(crate::errors::schema_error(
            "defaulted block holes require `as astichi_fallback`",
        ));
    }
    let resource_name = first_name_arg(call, "astichi_hole")?;
    records.push(record_with_owner(
        path,
        &authored_summary(&resource_name, source_map.line(node.range)),
        "hole.block",
        "splice-body-at-marker",
        "hole.block",
        &resource_name,
        "astichi.surface.block.hole",
        owner.to_vec(),
    ));
    Ok(())
}

fn direct_call_record(
    name: &str,
    node: &ast::ExprCall,
    path: &str,
    source_map: &SourceMap,
    context: ExprRecordContext,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    match name {
        "astichi_hole" => {
            let resource_name = first_name_arg(node, name)?;
            records.push(hole_record_for_context(
                path,
                &resource_name,
                source_map.line(node.range),
                context,
                owner.to_vec(),
            ));
            Ok(())
        }
        "astichi_bind_external" => {
            let resource_name = first_name_arg(node, name)?;
            records.push(external_record(
                path,
                &resource_name,
                source_map.line(node.range),
                owner.to_vec(),
            ));
            Ok(())
        }
        "astichi_ref" => {
            if let Some(resource_name) = external_keyword_name(node)? {
                records.push(external_record(
                    &(path.to_string() + "/args[0]"),
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            Ok(())
        }
        "astichi_export" => {
            let resource_name = first_name_arg(node, name)?;
            if is_assign_bind_identifier(&resource_name) {
                records.push(identifier_demand_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            records.push(identifier_supply_record(
                path,
                &resource_name,
                source_map.line(node.range),
                owner.to_vec(),
            ));
            Ok(())
        }
        "astichi_import" | "astichi_pass" => {
            let raw_resource_name = first_name_arg(node, name)?;
            let resource_name = strip_arg_suffix(&raw_resource_name).unwrap_or(raw_resource_name);
            records.push(record_with_owner(
                path,
                &authored_summary(&resource_name, source_map.line(node.range)),
                "identifier.demand",
                "rewrite-identifier",
                "identifier.demand",
                &resource_name,
                "astichi.surface.identifier.demand",
                owner.to_vec(),
            ));
            if is_assign_bind_identifier(&resource_name)
                && (name == "astichi_import"
                    || has_identifier_supply_record(records, &resource_name))
            {
                records.push(identifier_supply_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            Ok(())
        }
        "astichi_insert" => {
            validate_insert_call(node, InsertContext::Expression)?;
            let resource_name = first_name_arg(node, name)?;
            if matches!(
                context,
                ExprRecordContext::CallArgument
                    | ExprRecordContext::PositionalVariadic
                    | ExprRecordContext::NamedVariadic
            ) {
                records.push(hole_record_for_context(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    context,
                    owner.to_vec(),
                ));
            }
            records.push(expression_production_supply_record(
                path,
                &resource_name,
                source_map.line(node.range),
                owner.to_vec(),
            ));
            Ok(())
        }
        "astichi_comment" => Ok(()),
        "astichi_funcargs" => validate_funcargs_call(node),
        "astichi_keep" => {
            let resource_name = first_name_arg(node, name)?;
            if !matches!(context, ExprRecordContext::Statement) {
                return Ok(());
            }
            if is_assign_bind_identifier(&resource_name) {
                records.push(identifier_demand_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            if source_map.export_names.contains(&resource_name) {
                records.push(identifier_supply_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            } else if !is_assign_bind_identifier(&resource_name)
                && source_map.import_names.contains(&resource_name)
            {
                records.push(identifier_demand_record(
                    path,
                    &resource_name,
                    source_map.line(node.range),
                    owner.to_vec(),
                ));
            }
            Ok(())
        }
        "astichi_pyimport" => Ok(()),
        "astichi_for" => Ok(()),
        other if other.starts_with("astichi_") => Err(crate::errors::schema_error(&format!(
            "unsupported native direct call marker: {other}"
        ))),
        _ => Ok(()),
    }
}

fn decorator_records(
    decorators: &[ast::Expr],
    owner_path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    for (index, decorator) in decorators.iter().enumerate() {
        let ast::Expr::Call(node) = decorator else {
            continue;
        };
        if call_name(&node.func) != Some("astichi_insert") {
            continue;
        }
        validate_insert_call(node, InsertContext::Decorator)?;
        let resource_name = first_name_arg(node, "astichi_insert")?;
        let Some(kind) = matching_hole_record_kind(records, &resource_name) else {
            continue;
        };
        let path = format!("{owner_path}/decorator_list[{index}]");
        records.push(record_with_owner(
            &path,
            &authored_summary(&resource_name, source_map.line(node.range)),
            kind.role_key,
            kind.materialization_anchor,
            kind.inventory_kind,
            &resource_name,
            kind.surface_key,
            owner.to_vec(),
        ));
    }
    Ok(())
}

fn decorator_expr_records(
    decorators: &[ast::Expr],
    owner_path: &str,
    source_map: &SourceMap,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    for (index, decorator) in decorators.iter().enumerate() {
        if matches!(
            decorator,
            ast::Expr::Call(node) if call_name(&node.func) == Some("astichi_insert")
        ) {
            continue;
        }
        expr_records(
            decorator,
            &format!("{owner_path}/decorator_list[{index}]"),
            source_map,
            ExprRecordContext::Expression,
            owner,
            records,
        )?;
    }
    Ok(())
}

fn matching_hole_record_kind(
    records: &[ExtractedRecord],
    resource_name: &str,
) -> Option<InsertDecoratorKind> {
    for record in records {
        if record.resource_name != resource_name {
            continue;
        }
        match record.inventory_kind.as_str() {
            "hole.block" => {
                return Some(InsertDecoratorKind {
                    role_key: "hole.block",
                    materialization_anchor: "splice-body-at-marker",
                    inventory_kind: "hole.block",
                    surface_key: "astichi.surface.block.hole",
                });
            }
            "hole.params" => {
                return Some(InsertDecoratorKind {
                    role_key: "hole.params",
                    materialization_anchor: "splice-parameters",
                    inventory_kind: "hole.params",
                    surface_key: "astichi.surface.parameter.hole",
                });
            }
            "hole.elif" => {
                return Some(InsertDecoratorKind {
                    role_key: "hole.elif",
                    materialization_anchor: "append-clause",
                    inventory_kind: "hole.elif",
                    surface_key: "astichi.surface.elif.target",
                });
            }
            _ => {}
        }
    }
    None
}

#[derive(Clone, Copy)]
enum InsertContext {
    Decorator,
    Expression,
}

#[derive(Clone, Copy)]
struct InsertDecoratorKind {
    role_key: &'static str,
    materialization_anchor: &'static str,
    inventory_kind: &'static str,
    surface_key: &'static str,
}

fn insert_decorator_kind(node: &ast::ExprCall) -> PyResult<InsertDecoratorKind> {
    let mut kind = "block";
    for keyword in &node.keywords {
        if keyword.arg.as_ref().map(|arg| arg.as_str()) != Some("kind") {
            continue;
        }
        kind = string_constant(&keyword.value).ok_or_else(|| {
            crate::errors::schema_error("astichi_insert kind= must be a string constant")
        })?;
    }
    match kind {
        "block" => Ok(InsertDecoratorKind {
            role_key: "hole.block",
            materialization_anchor: "splice-body-at-marker",
            inventory_kind: "hole.block",
            surface_key: "astichi.surface.block.hole",
        }),
        "params" => Ok(InsertDecoratorKind {
            role_key: "hole.params",
            materialization_anchor: "splice-parameters",
            inventory_kind: "hole.params",
            surface_key: "astichi.surface.parameter.hole",
        }),
        "elif" => Ok(InsertDecoratorKind {
            role_key: "hole.elif",
            materialization_anchor: "append-clause",
            inventory_kind: "hole.elif",
            surface_key: "astichi.surface.elif.target",
        }),
        _ => Err(crate::errors::schema_error(
            "astichi_insert kind= must be the literal string 'block', 'elif', or 'params'",
        )),
    }
}

fn validate_insert_call(node: &ast::ExprCall, context: InsertContext) -> PyResult<()> {
    let expected_args = match context {
        InsertContext::Decorator => 1,
        InsertContext::Expression => 2,
    };
    if node.args.len() != expected_args {
        return Err(crate::errors::schema_error(
            "astichi_insert expects 1 positional argument (decorator) or 2 positional arguments (expression)",
        ));
    }
    let _ = first_name_arg(node, "astichi_insert")?;
    for keyword in &node.keywords {
        let Some(arg) = keyword.arg.as_ref().map(|arg| arg.as_str()) else {
            return Err(crate::errors::schema_error(
                "astichi_insert does not accept **kwargs",
            ));
        };
        match arg {
            "ref" => {
                if !matches!(context, InsertContext::Decorator) {
                    return Err(crate::errors::schema_error(
                        "astichi_insert ref= is only valid on decorator-form shells",
                    ));
                }
            }
            "kind" => {
                if !matches!(context, InsertContext::Decorator) {
                    return Err(crate::errors::schema_error(
                        "astichi_insert kind= is only valid on decorator-form shells",
                    ));
                }
                let _ = insert_decorator_kind(node)?;
            }
            "order" => {
                if !is_int_constant(&keyword.value) {
                    return Err(crate::errors::schema_error(
                        "astichi_insert order must be an integer constant",
                    ));
                }
            }
            "pyimport" => {
                if !matches!(context, InsertContext::Expression) {
                    return Err(crate::errors::schema_error(
                        "astichi_insert pyimport= is only valid on expression-form inserts",
                    ));
                }
                validate_insert_pyimport(&keyword.value)?;
            }
            _ => {
                return Err(crate::errors::schema_error(&format!(
                    "astichi_insert does not accept keyword `{arg}`"
                )));
            }
        }
    }
    Ok(())
}

fn validate_insert_pyimport(expr: &ast::Expr) -> PyResult<()> {
    let ast::Expr::Tuple(tuple) = expr else {
        return Err(crate::errors::schema_error(
            "astichi_insert pyimport= must be a tuple",
        ));
    };
    for element in &tuple.elts {
        if !is_call_named(element, "astichi_pyimport") {
            return Err(crate::errors::schema_error(
                "astichi_insert pyimport= entries must be astichi_pyimport(...) calls",
            ));
        }
    }
    Ok(())
}

fn string_constant(expr: &ast::Expr) -> Option<&str> {
    match expr {
        ast::Expr::Constant(node) => match &node.value {
            ast::Constant::Str(value) => Some(value.as_str()),
            _ => None,
        },
        _ => None,
    }
}

fn is_int_constant(expr: &ast::Expr) -> bool {
    match expr {
        ast::Expr::Constant(node) => matches!(node.value, ast::Constant::Int(_)),
        _ => false,
    }
}

fn first_name_arg(node: &ast::ExprCall, marker: &str) -> PyResult<String> {
    let Some(first) = node.args.first() else {
        return Err(crate::errors::schema_error(&format!(
            "{marker} requires a name argument"
        )));
    };
    match first {
        ast::Expr::Name(name) => Ok(name.id.to_string()),
        _ => Err(crate::errors::schema_error(&format!(
            "{marker} name argument must be a bare identifier"
        ))),
    }
}

fn first_name_arg_unchecked(node: &ast::ExprCall) -> Option<String> {
    match node.args.first()? {
        ast::Expr::Name(name) => Some(name.id.to_string()),
        _ => None,
    }
}

fn external_keyword_name(node: &ast::ExprCall) -> PyResult<Option<String>> {
    for keyword in &node.keywords {
        if keyword.arg.as_ref().map(|arg| arg.as_str()) != Some("external") {
            continue;
        }
        return match &keyword.value {
            ast::Expr::Name(name) => Ok(Some(name.id.to_string())),
            _ => Err(crate::errors::schema_error(
                "astichi_ref external argument must be a bare identifier",
            )),
        };
    }
    Ok(None)
}

fn external_record(
    path: &str,
    resource_name: &str,
    line_number: usize,
    owner: Vec<String>,
) -> ExtractedRecord {
    record_with_owner(
        path,
        &authored_summary(resource_name, line_number),
        "external.bind",
        "bind-external",
        "external.bind",
        resource_name,
        "astichi.surface.external.demand",
        owner,
    )
}

fn identifier_demand_record(
    path: &str,
    resource_name: &str,
    line_number: usize,
    owner: Vec<String>,
) -> ExtractedRecord {
    record_with_owner(
        path,
        &authored_summary(resource_name, line_number),
        "identifier.demand",
        "rewrite-identifier",
        "identifier.demand",
        resource_name,
        "astichi.surface.identifier.demand",
        owner,
    )
}

fn identifier_supply_record(
    path: &str,
    resource_name: &str,
    line_number: usize,
    owner: Vec<String>,
) -> ExtractedRecord {
    record_with_owner(
        path,
        &authored_summary(resource_name, line_number),
        "identifier.supply",
        "rewrite-identifier",
        "identifier.supply",
        resource_name,
        "astichi.surface.identifier.supply",
        owner,
    )
}

fn expression_production_supply_record(
    path: &str,
    resource_name: &str,
    line_number: usize,
    owner: Vec<String>,
) -> ExtractedRecord {
    record_with_owner(
        path,
        &authored_summary(resource_name, line_number),
        "production.supply",
        "copy-expression",
        "production.supply",
        resource_name,
        "astichi.surface.expression.production",
        owner,
    )
}

fn hole_record_for_context(
    path: &str,
    resource_name: &str,
    line_number: usize,
    context: ExprRecordContext,
    owner: Vec<String>,
) -> ExtractedRecord {
    let (role_key, materialization_anchor, inventory_kind, surface_key) = match context {
        ExprRecordContext::Statement => (
            "hole.block",
            "splice-body-at-marker",
            "hole.block",
            "astichi.surface.block.hole",
        ),
        ExprRecordContext::PositionalVariadic => (
            "hole.positional_variadic",
            "splice-call-arguments",
            "hole.positional_variadic",
            "astichi.surface.funcargs.hole",
        ),
        ExprRecordContext::NamedVariadic => (
            "hole.named_variadic",
            "splice-call-arguments",
            "hole.named_variadic",
            "astichi.surface.funcargs.hole",
        ),
        ExprRecordContext::Expression | ExprRecordContext::CallArgument => (
            "hole.expr",
            "replace-expression",
            "hole.expr",
            "astichi.surface.expression.hole",
        ),
    };
    record_with_owner(
        path,
        &authored_summary(resource_name, line_number),
        role_key,
        materialization_anchor,
        inventory_kind,
        resource_name,
        surface_key,
        owner,
    )
}

fn has_identifier_supply_record(records: &[ExtractedRecord], resource_name: &str) -> bool {
    records.iter().any(|record| {
        record.inventory_kind == "identifier.supply" && record.resource_name == resource_name
    })
}

fn block_production_record(line_number: usize) -> ExtractedRecord {
    record(
        ".",
        &authored_summary("__block__", line_number),
        "production.block",
        "copy-block",
        "production.block",
        "__block__",
        "astichi.surface.block.production",
    )
}

fn expression_production_record(path: &str, line_number: usize) -> ExtractedRecord {
    record(
        path,
        &authored_summary("__expr__", line_number),
        "production.expression",
        "copy-expression",
        "production.expression",
        "__expr__",
        "astichi.surface.expression.production",
    )
}

fn record(
    ast_path: &str,
    authored_summary: &str,
    role_key: &str,
    materialization_anchor: &str,
    inventory_kind: &str,
    resource_name: &str,
    surface_key: &str,
) -> ExtractedRecord {
    record_with_owner(
        ast_path,
        authored_summary,
        role_key,
        materialization_anchor,
        inventory_kind,
        resource_name,
        surface_key,
        Vec::new(),
    )
}

fn record_with_owner(
    ast_path: &str,
    authored_summary: &str,
    role_key: &str,
    materialization_anchor: &str,
    inventory_kind: &str,
    resource_name: &str,
    surface_key: &str,
    code_owner: Vec<String>,
) -> ExtractedRecord {
    let owner_summary = if code_owner.is_empty() {
        ".".to_string()
    } else {
        code_owner.join("/")
    };
    ExtractedRecord {
        ast_path: ast_path.to_string(),
        authored_summary: authored_summary.to_string(),
        role_key: role_key.to_string(),
        materialization_anchor: materialization_anchor.to_string(),
        inventory_kind: inventory_kind.to_string(),
        resource_name: resource_name.to_string(),
        semantic_summary: format!(
            "{inventory_kind} name={resource_name} owner={owner_summary} build_path=."
        ),
        surface_key: surface_key.to_string(),
        code_owner,
    }
}

fn authored_summary(resource_name: &str, line_number: usize) -> String {
    format!("{resource_name} at line {line_number}")
}

fn strip_arg_suffix(value: &str) -> Option<String> {
    value
        .strip_suffix(ARG_SUFFIX)
        .map(|stripped| stripped.to_string())
}

fn strip_param_hole_suffix(value: &str) -> Option<String> {
    value
        .strip_suffix(PARAM_HOLE_SUFFIX)
        .map(|stripped| stripped.to_string())
}

fn strip_known_suffix(value: &str) -> String {
    value
        .strip_suffix(ARG_SUFFIX)
        .or_else(|| value.strip_suffix(PARAM_HOLE_SUFFIX))
        .or_else(|| value.strip_suffix(KEEP_SUFFIX))
        .unwrap_or(value)
        .to_string()
}

/// Template cache identity: SHA-256 of UTF-8 registration source (first 16 hex digits).
pub(crate) fn template_key_from_source(source: &str) -> String {
    use sha2::{Digest, Sha256};
    let digest = format!("{:x}", Sha256::digest(source.as_bytes()));
    format!("template:{}", &digest[..16])
}

pub(crate) fn native_template_key(
    _py: Python<'_>,
    source: &str,
    _module: &ast::ModModule,
    _source_summary: &str,
) -> PyResult<String> {
    Ok(template_key_from_source(source))
}

/// Alias kept for call sites that already name the source-only entry point.
pub(crate) fn native_template_key_from_source(source: &str) -> String {
    template_key_from_source(source)
}

fn structural_snapshot(
    py: Python<'_>,
    surface_bundle: Py<PyAny>,
    template_key: &str,
    source_summary: &str,
    records: &[ExtractedRecord],
) -> PyResult<Py<PyAny>> {
    let snapshot = PyDict::new(py);
    snapshot.set_item("schema", STRUCTURAL_SCHEMA)?;
    snapshot.set_item("surface_bundle", surface_bundle)?;
    snapshot.set_item(
        "templates",
        templates(py, template_key, source_summary, records.len())?,
    )?;
    snapshot.set_item("locators", locators(py, records)?)?;
    snapshot.set_item("occurrences", occurrences(py)?)?;
    snapshot.set_item("records", record_snapshots(py, records)?)?;
    snapshot.set_item("edges", PyList::empty(py))?;
    snapshot.set_item("overlays", PyList::empty(py))?;
    snapshot.set_item("materialization", materialization(py)?)?;
    snapshot.set_item("diagnostics", PyList::empty(py))?;
    Ok(snapshot.into_any().unbind())
}

fn templates(
    py: Python<'_>,
    template_key: &str,
    source_summary: &str,
    record_count: usize,
) -> PyResult<Py<PyAny>> {
    let item = PyDict::new(py);
    item.set_item("record_count", record_count)?;
    item.set_item("source_summary", source_summary)?;
    item.set_item("template_id", 0)?;
    item.set_item("template_key", template_key)?;
    let list = PyList::empty(py);
    list.append(item)?;
    Ok(list.into_any().unbind())
}

fn locators(py: Python<'_>, records: &[ExtractedRecord]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (index, record) in records.iter().enumerate() {
        let item = PyDict::new(py);
        item.set_item("ast_path", &record.ast_path)?;
        item.set_item("authored_summary", &record.authored_summary)?;
        item.set_item("locator_id", index)?;
        item.set_item("materialization_anchor", &record.materialization_anchor)?;
        item.set_item("parent_locator_id", py.None())?;
        item.set_item("role_key", &record.role_key)?;
        item.set_item("template_id", 0)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn occurrences(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let item = PyDict::new(py);
    item.set_item("build_path", vec!["Template"])?;
    item.set_item("occurrence_id", 0)?;
    item.set_item("parent_occurrence_id", py.None())?;
    item.set_item("template_id", 0)?;
    let list = PyList::empty(py);
    list.append(item)?;
    Ok(list.into_any().unbind())
}

fn record_snapshots(py: Python<'_>, records: &[ExtractedRecord]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (index, record) in records.iter().enumerate() {
        let item = PyDict::new(py);
        item.set_item("code_owner", &record.code_owner)?;
        item.set_item("inventory_kind", &record.inventory_kind)?;
        item.set_item("locator_id", index)?;
        item.set_item("occurrence_id", 0)?;
        item.set_item("record_id", vec![0, index])?;
        item.set_item("resource_name", &record.resource_name)?;
        item.set_item("semantic_summary", &record.semantic_summary)?;
        let state = PyDict::new(py);
        state.set_item("satisfied", false)?;
        state.set_item("visible", true)?;
        item.set_item("state", state)?;
        item.set_item("surface_key", &record.surface_key)?;
        item.set_item("template_record_id", index)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn materialization(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let item = PyDict::new(py);
    item.set_item("artifact_requests", PyList::empty(py))?;
    item.set_item("debug_views", PyDict::new(py))?;
    item.set_item("hygiene_stream", PyList::empty(py))?;
    item.set_item("operation_stream", PyList::empty(py))?;
    item.set_item("root_occurrence_id", py.None())?;
    Ok(item.into_any().unbind())
}
