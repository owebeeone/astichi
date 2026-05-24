use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyModule};
use rustpython_parser::ast;
use rustpython_parser::text_size::TextRange;

use crate::handles::EngineHandle;

const STRUCTURAL_SCHEMA: &str = "astichi.structural-inventory.v1";
const ARG_SUFFIX: &str = "__astichi_arg__";
const KEEP_SUFFIX: &str = "__astichi_keep__";

#[derive(Clone)]
struct SourceMap {
    line_starts: Vec<usize>,
}

impl SourceMap {
    fn new(source: &str) -> Self {
        let mut line_starts = vec![0];
        for (idx, byte) in source.bytes().enumerate() {
            if byte == b'\n' {
                line_starts.push(idx + 1);
            }
        }
        Self { line_starts }
    }

    fn line(&self, range: TextRange) -> usize {
        let offset = range.start().to_u32() as usize;
        match self.line_starts.binary_search(&offset) {
            Ok(idx) => idx + 1,
            Err(idx) => idx,
        }
    }
}

#[derive(Clone)]
struct ExtractedRecord {
    ast_path: String,
    authored_summary: String,
    role_key: String,
    materialization_anchor: String,
    inventory_kind: String,
    resource_name: String,
    semantic_summary: String,
    surface_key: String,
    code_owner: Vec<String>,
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

    reject_deferred_markers(&source)?;
    let filename = filename.unwrap_or_else(|| "<astichi-native>".to_string());
    let module = crate::parser_ir::parse_native_module(&source, &filename)?;
    let mut records = extract_records(&source, &module)?;
    if should_include_block_production(&module) {
        let source_map = SourceMap::new(&source);
        records.push(block_production_record(block_production_line_number(
            &module,
            &source_map,
            line_number,
        )));
    }

    let source_summary = "compile line=".to_string()
        + &line_number.to_string()
        + " records="
        + &records.len().to_string();
    let ast_dump = crate::parser_ir::ast_dump_without_attributes(py, &source, &module)?;
    let template_key = template_key(py, &ast_dump, &source_summary)?;

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
    Ok(())
}

fn reject_deferred_markers(source: &str) -> PyResult<()> {
    validate_deferred_marker_text(source)?;
    Ok(())
}

fn validate_deferred_marker_text(_source: &str) -> PyResult<()> {
    Ok(())
}

fn extract_records(source: &str, module: &ast::ModModule) -> PyResult<Vec<ExtractedRecord>> {
    let source_map = SourceMap::new(source);
    let mut records = Vec::new();
    for (index, stmt) in module.body.iter().enumerate() {
        stmt_records(
            stmt,
            &format!("body[{index}]"),
            &source_map,
            &[],
            &mut records,
        )?;
    }
    if let Some(record) = root_funcargs_production_record(module, &source_map) {
        records.push(record);
    }
    if let Some(record) = implicit_expression_production_record(module, &source_map) {
        records.push(record);
    }
    Ok(records)
}

fn root_funcargs_production_record(
    module: &ast::ModModule,
    source_map: &SourceMap,
) -> Option<ExtractedRecord> {
    let ast::Stmt::Expr(stmt) = single_root_statement(module)? else {
        return None;
    };
    if !is_call_named(&stmt.value, "astichi_funcargs") {
        return None;
    }
    Some(record(
        "body[0]/value",
        &authored_summary("__funcargs__", source_map.line(stmt.range)),
        "production.funcargs",
        "copy-call-arguments",
        "production.funcargs",
        "__funcargs__",
        "astichi.surface.funcargs.production",
    ))
}

fn implicit_expression_production_record(
    module: &ast::ModModule,
    source_map: &SourceMap,
) -> Option<ExtractedRecord> {
    let mut expression: Option<(&ast::Expr, String, usize)> = None;
    for (index, stmt) in module.body.iter().enumerate() {
        if is_boundary_prefix_statement(stmt) {
            continue;
        }
        let ast::Stmt::Expr(expr_stmt) = stmt else {
            return None;
        };
        if expression.is_some() {
            return None;
        }
        if is_call_named(&expr_stmt.value, "astichi_insert")
            || is_call_named(&expr_stmt.value, "astichi_funcargs")
        {
            return None;
        }
        expression = Some((
            &expr_stmt.value,
            format!("body[{index}]/value"),
            source_map.line(expr_stmt.range),
        ));
    }
    let (_expr, path, line_number) = expression?;
    Some(expression_production_record(&path, line_number))
}

fn single_root_statement(module: &ast::ModModule) -> Option<&ast::Stmt> {
    if module.body.len() == 1 {
        Some(&module.body[0])
    } else {
        None
    }
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

fn should_include_block_production(module: &ast::ModModule) -> bool {
    if module.body.len() != 1 {
        return true;
    }
    match &module.body[0] {
        ast::Stmt::FunctionDef(node) => node.name.as_str() != "astichi_params",
        ast::Stmt::Expr(node) => !is_call_named(&node.value, "astichi_funcargs"),
        _ => true,
    }
}

fn block_production_line_number(
    module: &ast::ModModule,
    source_map: &SourceMap,
    fallback: u32,
) -> usize {
    let Some(stmt) = module.body.first() else {
        return fallback as usize;
    };
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
        _ => fallback as usize,
    }
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
                true,
                owner,
                records,
            )?;
            Ok(())
        }
        ast::Stmt::Assign(node) => expr_records(
            &node.value,
            &(path.to_string() + "/value"),
            source_map,
            false,
            owner,
            records,
        ),
        ast::Stmt::AnnAssign(node) => {
            expr_records(
                &node.annotation,
                &(path.to_string() + "/annotation"),
                source_map,
                false,
                owner,
                records,
            )?;
            if let Some(value) = node.value.as_ref() {
                expr_records(
                    value,
                    &(path.to_string() + "/value"),
                    source_map,
                    false,
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
                    false,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
        ast::Stmt::FunctionDef(node) => {
            let function_owner = child_owner(owner, node.name.as_str());
            if node.name.as_str() == "astichi_params" {
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
                );
                return Ok(());
            }
            if let Some(resource_name) = strip_arg_suffix(node.name.as_str()) {
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
            );
            for (index, stmt) in node.body.iter().enumerate() {
                stmt_records(
                    stmt,
                    &format!("{path}/body[{index}]"),
                    source_map,
                    &function_owner,
                    records,
                )?;
            }
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

fn expr_records(
    expr: &ast::Expr,
    path: &str,
    source_map: &SourceMap,
    in_expr_stmt: bool,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    match expr {
        ast::Expr::Call(node) => {
            let name = call_name(&node.func);
            if let Some(name) = name {
                direct_call_record(name, node, path, source_map, in_expr_stmt, owner, records)?;
            }
            for (index, arg) in node.args.iter().enumerate() {
                expr_records(
                    arg,
                    &format!("{path}/args[{index}]"),
                    source_map,
                    false,
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
                expr_records(
                    &keyword.value,
                    &format!("{path}/keywords[{index}]/value"),
                    source_map,
                    false,
                    owner,
                    records,
                )?;
            }
            Ok(())
        }
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
        ast::Expr::BoolOp(node) => {
            for (index, value) in node.values.iter().enumerate() {
                expr_records(
                    value,
                    &format!("{path}/values[{index}]"),
                    source_map,
                    false,
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
                false,
                owner,
                records,
            )?;
            expr_records(
                &node.right,
                &(path.to_string() + "/right"),
                source_map,
                false,
                owner,
                records,
            )
        }
        ast::Expr::UnaryOp(node) => expr_records(
            &node.operand,
            &(path.to_string() + "/operand"),
            source_map,
            false,
            owner,
            records,
        ),
        ast::Expr::IfExp(node) => {
            expr_records(
                &node.test,
                &(path.to_string() + "/test"),
                source_map,
                false,
                owner,
                records,
            )?;
            expr_records(
                &node.body,
                &(path.to_string() + "/body"),
                source_map,
                false,
                owner,
                records,
            )?;
            expr_records(
                &node.orelse,
                &(path.to_string() + "/orelse"),
                source_map,
                false,
                owner,
                records,
            )
        }
        _ => Ok(()),
    }
}

fn call_name(expr: &ast::Expr) -> Option<&str> {
    match expr {
        ast::Expr::Name(node) => Some(node.id.as_str()),
        _ => None,
    }
}

fn is_call_named(expr: &ast::Expr, name: &str) -> bool {
    match expr {
        ast::Expr::Call(node) => call_name(&node.func) == Some(name),
        _ => false,
    }
}

fn function_argument_suffix_records(
    args: &ast::Arguments,
    path: &str,
    owner: &[String],
    source_map: &SourceMap,
    records: &mut Vec<ExtractedRecord>,
) {
    for (index, arg) in args.posonlyargs.iter().enumerate() {
        arg_suffix_record(
            &arg.def,
            &format!("{path}/args/posonlyargs[{index}]"),
            source_map,
            owner.to_vec(),
            records,
        );
    }
    for (index, arg) in args.args.iter().enumerate() {
        arg_suffix_record(
            &arg.def,
            &format!("{path}/args/args[{index}]"),
            source_map,
            owner.to_vec(),
            records,
        );
    }
    for (index, arg) in args.kwonlyargs.iter().enumerate() {
        arg_suffix_record(
            &arg.def,
            &format!("{path}/args/kwonlyargs[{index}]"),
            source_map,
            owner.to_vec(),
            records,
        );
    }
    if let Some(arg) = args.vararg.as_ref() {
        arg_suffix_record(
            arg,
            &(path.to_string() + "/args/vararg"),
            source_map,
            owner.to_vec(),
            records,
        );
    }
    if let Some(arg) = args.kwarg.as_ref() {
        arg_suffix_record(
            arg,
            &(path.to_string() + "/args/kwarg"),
            source_map,
            owner.to_vec(),
            records,
        );
    }
}

fn arg_suffix_record(
    arg: &ast::Arg,
    path: &str,
    source_map: &SourceMap,
    owner: Vec<String>,
    records: &mut Vec<ExtractedRecord>,
) {
    if let Some(resource_name) = strip_arg_suffix(arg.arg.as_str()) {
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

fn direct_call_record(
    name: &str,
    node: &ast::ExprCall,
    path: &str,
    source_map: &SourceMap,
    in_expr_stmt: bool,
    owner: &[String],
    records: &mut Vec<ExtractedRecord>,
) -> PyResult<()> {
    match name {
        "astichi_hole" => {
            let resource_name = first_name_arg(node, name)?;
            if in_expr_stmt {
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
            } else {
                records.push(record_with_owner(
                    path,
                    &authored_summary(&resource_name, source_map.line(node.range)),
                    "hole.expr",
                    "replace-expression",
                    "hole.expr",
                    &resource_name,
                    "astichi.surface.expression.hole",
                    owner.to_vec(),
                ));
            }
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
            records.push(record_with_owner(
                path,
                &authored_summary(&resource_name, source_map.line(node.range)),
                "identifier.supply",
                "rewrite-identifier",
                "identifier.supply",
                &resource_name,
                "astichi.surface.identifier.supply",
                owner.to_vec(),
            ));
            Ok(())
        }
        "astichi_import" | "astichi_pass" => {
            let resource_name = first_name_arg(node, name)?;
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
            Ok(())
        }
        "astichi_insert" => {
            validate_insert_call(node, InsertContext::Expression)?;
            let resource_name = first_name_arg(node, name)?;
            records.push(record_with_owner(
                path,
                &authored_summary(&resource_name, source_map.line(node.range)),
                "production.supply",
                "copy-expression",
                "production.supply",
                &resource_name,
                "astichi.surface.expression.production",
                owner.to_vec(),
            ));
            Ok(())
        }
        "astichi_comment" => Ok(()),
        "astichi_funcargs" => Ok(()),
        "astichi_keep" | "astichi_pyimport" => Ok(()),
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

fn strip_known_suffix(value: &str) -> String {
    value
        .strip_suffix(ARG_SUFFIX)
        .or_else(|| value.strip_suffix(KEEP_SUFFIX))
        .unwrap_or(value)
        .to_string()
}

fn template_key(py: Python<'_>, ast_dump: &str, source_summary: &str) -> PyResult<String> {
    let payload = ast_dump.to_string() + "\n" + source_summary;
    let digest: String = py
        .import("hashlib")?
        .getattr("sha256")?
        .call1((PyBytes::new(py, payload.as_bytes()),))?
        .getattr("hexdigest")?
        .call0()?
        .extract()?;
    Ok("template:".to_string() + &digest[..16])
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
