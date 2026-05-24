use pyo3::exceptions::{PyNotImplementedError, PySyntaxError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyModule};
use rustpython_parser::ast;
use rustpython_parser::text_size::TextRange;
use rustpython_parser::Parse;
use std::collections::BTreeMap;
use std::time::Instant;

pub const PARSER_BACKEND: &str = "rustpython-parser 0.4.0";

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

    fn point(&self, offset: usize) -> (usize, usize) {
        let line_idx = match self.line_starts.binary_search(&offset) {
            Ok(idx) => idx,
            Err(idx) => idx.saturating_sub(1),
        };
        let col = offset.saturating_sub(self.line_starts[line_idx]);
        (line_idx + 1, col)
    }

    fn range(&self, range: TextRange) -> (usize, usize, usize, usize) {
        let start = range.start().to_u32() as usize;
        let end = range.end().to_u32() as usize;
        let (lineno, col_offset) = self.point(start);
        let (end_lineno, end_col_offset) = self.point(end);
        (lineno, col_offset, end_lineno, end_col_offset)
    }
}

#[derive(Default, Clone)]
struct EmitStats {
    nodes_constructed: usize,
    required_default_fields: usize,
    location_fields: usize,
    constructor_ns: u128,
    field_population_ns: u128,
    location_ns: u128,
}

impl EmitStats {
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("nodes_constructed", self.nodes_constructed)?;
        dict.set_item("required_default_fields", self.required_default_fields)?;
        dict.set_item("location_fields", self.location_fields)?;
        dict.set_item("constructor_seconds", ns_to_secs(self.constructor_ns))?;
        dict.set_item(
            "required_default_field_population_seconds",
            ns_to_secs(self.field_population_ns),
        )?;
        dict.set_item("location_population_seconds", ns_to_secs(self.location_ns))?;
        Ok(dict.unbind())
    }
}

#[pyclass(name = "NativeModule", module = "_astichi_native_engine")]
struct LowerComposable {
    source: String,
    filename: String,
    module: ast::ModModule,
    node_counts: BTreeMap<String, usize>,
}

#[pymethods]
impl LowerComposable {
    #[getter]
    fn filename(&self) -> &str {
        &self.filename
    }

    #[getter]
    fn parser_backend(&self) -> &str {
        PARSER_BACKEND
    }

    fn node_counts(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        dict_from_counts(py, &self.node_counts)
    }

    #[pyo3(signature = (location_policy = "native"))]
    fn copy_to_python_ast(&self, py: Python<'_>, location_policy: &str) -> PyResult<Py<PyAny>> {
        convert_module_artifact(py, &self.source, &self.module, location_policy).map(|v| v.0)
    }

    #[pyo3(signature = (location_policy = "native"))]
    fn to_source(&self, py: Python<'_>, location_policy: &str) -> PyResult<String> {
        let module = self.copy_to_python_ast(py, location_policy)?;
        let ast_mod = py.import("ast")?;
        ast_mod.getattr("unparse")?.call1((module,))?.extract()
    }

    fn __repr__(&self) -> String {
        format!(
            "NativeModule(filename={:?}, backend={:?}, nodes={})",
            self.filename,
            PARSER_BACKEND,
            self.node_counts.values().sum::<usize>()
        )
    }
}

fn parse_native(source: &str, filename: &str) -> Result<ast::ModModule, String> {
    ast::ModModule::parse(source, filename).map_err(|err| err.to_string())
}

fn parse_native_timed(source: String, filename: String) -> (Result<ast::ModModule, String>, u128) {
    let start = Instant::now();
    let parsed = parse_native(&source, &filename);
    (parsed, start.elapsed().as_nanos())
}

fn syntax_err(message: String, filename: &str) -> PyErr {
    PySyntaxError::new_err(format!("{message} in {filename}"))
}

fn unsupported(message: impl Into<String>) -> PyErr {
    PyNotImplementedError::new_err(message.into())
}

fn ns_to_secs(ns: u128) -> f64 {
    ns as f64 / 1_000_000_000.0
}

#[pyfunction]
#[pyo3(signature = (source, filename = None, location_policy = "native"))]
fn parse_module(
    py: Python<'_>,
    source: String,
    filename: Option<String>,
    location_policy: &str,
) -> PyResult<Py<PyAny>> {
    let filename = filename.unwrap_or_else(|| "<astichi-native>".to_string());
    let source_for_parse = source.clone();
    let filename_for_parse = filename.clone();
    let (parsed, _) = py.detach(move || parse_native_timed(source_for_parse, filename_for_parse));
    let module = parsed.map_err(|message| syntax_err(message, &filename))?;
    convert_module_artifact(py, &source, &module, location_policy).map(|v| v.0)
}

#[pyfunction]
#[pyo3(signature = (source, filename = None))]
fn compile_composable(
    py: Python<'_>,
    source: String,
    filename: Option<String>,
) -> PyResult<LowerComposable> {
    let filename = filename.unwrap_or_else(|| "<astichi-native>".to_string());
    let source_for_parse = source.clone();
    let filename_for_parse = filename.clone();
    let (parsed, _) = py.detach(move || parse_native_timed(source_for_parse, filename_for_parse));
    let module = parsed.map_err(|message| syntax_err(message, &filename))?;
    let node_counts = count_module(&module);
    Ok(LowerComposable {
        source,
        filename,
        module,
        node_counts,
    })
}

#[pyfunction]
#[pyo3(signature = (composable, location_policy = "native"))]
fn copy_to_python_ast(
    py: Python<'_>,
    composable: PyRef<'_, LowerComposable>,
    location_policy: &str,
) -> PyResult<Py<PyAny>> {
    convert_module_artifact(py, &composable.source, &composable.module, location_policy)
        .map(|v| v.0)
}

#[pyfunction]
#[pyo3(signature = (composable, location_policy = "native"))]
fn to_source(
    py: Python<'_>,
    composable: PyRef<'_, LowerComposable>,
    location_policy: &str,
) -> PyResult<String> {
    let module =
        convert_module_artifact(py, &composable.source, &composable.module, location_policy)?.0;
    let ast_mod = py.import("ast")?;
    ast_mod.getattr("unparse")?.call1((module,))?.extract()
}

#[pyfunction]
#[pyo3(signature = (source, iterations, filename = None, location_policy = "native"))]
fn bench_parse_convert(
    py: Python<'_>,
    source: String,
    iterations: usize,
    filename: Option<String>,
    location_policy: &str,
) -> PyResult<Py<PyDict>> {
    let filename = filename.unwrap_or_else(|| "<astichi-native>".to_string());
    if iterations == 0 {
        return Err(PyValueError::new_err(
            "iterations must be greater than zero",
        ));
    }

    let parse_source = source.clone();
    let parse_filename = filename.clone();
    let parse_start = Instant::now();
    let parse_result: Result<ast::ModModule, String> = py.detach(move || {
        let mut last = None;
        for _ in 0..iterations {
            last = Some(parse_native(&parse_source, &parse_filename)?);
        }
        Ok(last.expect("iterations checked above"))
    });
    let parsed = parse_result.map_err(|message| syntax_err(message, &filename))?;
    let parse_ns = parse_start.elapsed().as_nanos();

    let count_start = Instant::now();
    let counts = count_module(&parsed);
    let count_ns = count_start.elapsed().as_nanos();

    let copy_start = Instant::now();
    let mut last_stats = EmitStats::default();
    for _ in 0..iterations {
        let (_, stats) = convert_module_artifact(py, &source, &parsed, location_policy)?;
        last_stats = stats;
    }
    let copy_ns = copy_start.elapsed().as_nanos();

    let dict = PyDict::new(py);
    dict.set_item("parser_backend", PARSER_BACKEND)?;
    dict.set_item("iterations", iterations)?;
    dict.set_item("native_parse_seconds", ns_to_secs(parse_ns))?;
    dict.set_item("native_ast_or_ir_count_seconds", ns_to_secs(count_ns))?;
    dict.set_item("artifact_copy_seconds", ns_to_secs(copy_ns))?;
    dict.set_item("cpython_ast_construction_seconds", ns_to_secs(copy_ns))?;
    dict.set_item("emit_stats", last_stats.to_dict(py)?)?;
    dict.set_item("node_counts", dict_from_counts(py, &counts)?)?;
    dict.set_item("source_bytes", source.len())?;
    dict.set_item(
        "gil_notes",
        "native parsing runs inside Python::detach; CPython AST construction holds the GIL",
    )?;
    Ok(dict.unbind())
}

#[pyfunction]
fn parser_backend() -> &'static str {
    PARSER_BACKEND
}

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<LowerComposable>()?;
    m.add_function(wrap_pyfunction!(parse_module, m)?)?;
    m.add_function(wrap_pyfunction!(compile_composable, m)?)?;
    m.add_function(wrap_pyfunction!(copy_to_python_ast, m)?)?;
    m.add_function(wrap_pyfunction!(to_source, m)?)?;
    m.add_function(wrap_pyfunction!(bench_parse_convert, m)?)?;
    m.add_function(wrap_pyfunction!(parser_backend, m)?)?;
    Ok(())
}

fn convert_module_artifact(
    py: Python<'_>,
    source: &str,
    module: &ast::ModModule,
    location_policy: &str,
) -> PyResult<(Py<PyAny>, EmitStats)> {
    let set_locations = match location_policy {
        "native" => true,
        "fix_missing" => false,
        other => {
            return Err(PyValueError::new_err(format!(
                "unknown location_policy {other:?}; expected 'native' or 'fix_missing'"
            )))
        }
    };
    let mut emitter = Emitter::new(py, source, set_locations)?;
    let obj = emitter.module(module)?;
    let stats = emitter.stats.clone();
    if set_locations {
        Ok((obj, stats))
    } else {
        let fixed = emitter
            .ast_mod
            .getattr("fix_missing_locations")?
            .call1((obj,))?
            .unbind();
        Ok((fixed, stats))
    }
}

struct Emitter<'py> {
    py: Python<'py>,
    ast_mod: Bound<'py, PyModule>,
    source_map: SourceMap,
    set_locations: bool,
    stats: EmitStats,
}

impl<'py> Emitter<'py> {
    fn new(py: Python<'py>, source: &str, set_locations: bool) -> PyResult<Self> {
        Ok(Self {
            py,
            ast_mod: py.import("ast")?,
            source_map: SourceMap::new(source),
            set_locations,
            stats: EmitStats::default(),
        })
    }

    fn list(&mut self, items: Vec<Py<PyAny>>) -> PyResult<Py<PyAny>> {
        let start = Instant::now();
        let list = PyList::new(self.py, items)?.into_any().unbind();
        self.stats.required_default_fields += 1;
        self.stats.field_population_ns += start.elapsed().as_nanos();
        Ok(list)
    }

    fn none(&self) -> Py<PyAny> {
        self.py.None()
    }

    fn optional_expr(&mut self, value: Option<&Box<ast::Expr>>) -> PyResult<Py<PyAny>> {
        match value {
            Some(expr) => self.expr(expr),
            None => Ok(self.none()),
        }
    }

    fn optional_arg(&mut self, value: Option<&Box<ast::Arg>>) -> PyResult<Py<PyAny>> {
        match value {
            Some(arg) => self.arg(arg),
            None => Ok(self.none()),
        }
    }

    fn optional_identifier(&self, value: Option<&ast::Identifier>) -> Py<PyAny> {
        match value {
            Some(identifier) => identifier
                .to_string()
                .into_pyobject(self.py)
                .unwrap()
                .unbind()
                .into(),
            None => self.none(),
        }
    }

    fn call_ast<A>(&mut self, name: &str, args: A) -> PyResult<Bound<'py, PyAny>>
    where
        A: pyo3::call::PyCallArgs<'py>,
    {
        let start = Instant::now();
        let obj = self.ast_mod.getattr(name)?.call1(args)?;
        self.stats.nodes_constructed += 1;
        self.stats.constructor_ns += start.elapsed().as_nanos();
        Ok(obj)
    }

    fn simple(&mut self, name: &str) -> PyResult<Py<PyAny>> {
        let start = Instant::now();
        let obj = self.ast_mod.getattr(name)?.call0()?.unbind();
        self.stats.nodes_constructed += 1;
        self.stats.constructor_ns += start.elapsed().as_nanos();
        Ok(obj)
    }

    fn set_location(&mut self, obj: &Bound<'py, PyAny>, range: TextRange) -> PyResult<()> {
        if !self.set_locations {
            return Ok(());
        }
        let start = Instant::now();
        let (lineno, col_offset, end_lineno, end_col_offset) = self.source_map.range(range);
        obj.setattr("lineno", lineno)?;
        obj.setattr("col_offset", col_offset)?;
        obj.setattr("end_lineno", end_lineno)?;
        obj.setattr("end_col_offset", end_col_offset)?;
        self.stats.location_fields += 4;
        self.stats.location_ns += start.elapsed().as_nanos();
        Ok(())
    }

    fn module(&mut self, module: &ast::ModModule) -> PyResult<Py<PyAny>> {
        let body = self.stmt_list(&module.body)?;
        let type_ignores = self.type_ignore_list(&module.type_ignores)?;
        Ok(self.call_ast("Module", (body, type_ignores))?.unbind())
    }

    fn stmt_list(&mut self, stmts: &[ast::Stmt]) -> PyResult<Py<PyAny>> {
        let mut items = Vec::with_capacity(stmts.len());
        for stmt in stmts {
            items.push(self.stmt(stmt)?);
        }
        self.list(items)
    }

    fn expr_list(&mut self, exprs: &[ast::Expr]) -> PyResult<Py<PyAny>> {
        let mut items = Vec::with_capacity(exprs.len());
        for expr in exprs {
            items.push(self.expr(expr)?);
        }
        self.list(items)
    }

    fn optional_expr_list(&mut self, exprs: &[Option<ast::Expr>]) -> PyResult<Py<PyAny>> {
        let mut items = Vec::with_capacity(exprs.len());
        for expr in exprs {
            items.push(match expr {
                Some(expr) => self.expr(expr)?,
                None => self.none(),
            });
        }
        self.list(items)
    }

    fn string_list(&mut self, values: &[ast::Identifier]) -> PyResult<Py<PyAny>> {
        let mut items = Vec::with_capacity(values.len());
        for value in values {
            items.push(value.to_string().into_pyobject(self.py)?.unbind().into());
        }
        self.list(items)
    }

    fn stmt(&mut self, stmt: &ast::Stmt) -> PyResult<Py<PyAny>> {
        match stmt {
            ast::Stmt::FunctionDef(node) => self.function_def(node, false),
            ast::Stmt::AsyncFunctionDef(node) => self.async_function_def(node),
            ast::Stmt::ClassDef(node) => self.class_def(node),
            ast::Stmt::Return(node) => {
                let value = self.optional_expr(node.value.as_ref())?;
                let obj = self.call_ast("Return", (value,))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Assign(node) => {
                let targets = self.expr_list(&node.targets)?;
                let value = self.expr(&node.value)?;
                let type_comment = match &node.type_comment {
                    Some(value) => value.clone().into_pyobject(self.py)?.unbind().into(),
                    None => self.none(),
                };
                let obj = self.call_ast("Assign", (targets, value, type_comment))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::AnnAssign(node) => {
                let target = self.expr(&node.target)?;
                let annotation = self.expr(&node.annotation)?;
                let value = self.optional_expr(node.value.as_ref())?;
                let obj = self.call_ast("AnnAssign", (target, annotation, value, node.simple))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::For(node) => {
                let target = self.expr(&node.target)?;
                let iter = self.expr(&node.iter)?;
                let body = self.stmt_list(&node.body)?;
                let orelse = self.stmt_list(&node.orelse)?;
                let type_comment = match &node.type_comment {
                    Some(value) => value.clone().into_pyobject(self.py)?.unbind().into(),
                    None => self.none(),
                };
                let obj = self.call_ast("For", (target, iter, body, orelse, type_comment))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::While(node) => {
                let test = self.expr(&node.test)?;
                let body = self.stmt_list(&node.body)?;
                let orelse = self.stmt_list(&node.orelse)?;
                let obj = self.call_ast("While", (test, body, orelse))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::If(node) => {
                let test = self.expr(&node.test)?;
                let body = self.stmt_list(&node.body)?;
                let orelse = self.stmt_list(&node.orelse)?;
                let obj = self.call_ast("If", (test, body, orelse))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::With(node) => {
                let items = self.with_item_list(&node.items)?;
                let body = self.stmt_list(&node.body)?;
                let type_comment = match &node.type_comment {
                    Some(value) => value.clone().into_pyobject(self.py)?.unbind().into(),
                    None => self.none(),
                };
                let obj = self.call_ast("With", (items, body, type_comment))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Try(node) => {
                let body = self.stmt_list(&node.body)?;
                let handlers = self.except_handler_list(&node.handlers)?;
                let orelse = self.stmt_list(&node.orelse)?;
                let finalbody = self.stmt_list(&node.finalbody)?;
                let obj = self.call_ast("Try", (body, handlers, orelse, finalbody))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Assert(node) => {
                let test = self.expr(&node.test)?;
                let msg = self.optional_expr(node.msg.as_ref())?;
                let obj = self.call_ast("Assert", (test, msg))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Raise(node) => {
                let exc = self.optional_expr(node.exc.as_ref())?;
                let cause = self.optional_expr(node.cause.as_ref())?;
                let obj = self.call_ast("Raise", (exc, cause))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Import(node) => {
                let names = self.alias_list(&node.names)?;
                let obj = self.call_ast("Import", (names,))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::ImportFrom(node) => {
                let module = self.optional_identifier(node.module.as_ref());
                let names = self.alias_list(&node.names)?;
                let level = node.level.map(|value| value.to_u32()).unwrap_or(0);
                let obj = self.call_ast("ImportFrom", (module, names, level))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Global(node) => {
                let names = self.string_list(&node.names)?;
                let obj = self.call_ast("Global", (names,))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Nonlocal(node) => {
                let names = self.string_list(&node.names)?;
                let obj = self.call_ast("Nonlocal", (names,))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Expr(node) => {
                let value = self.expr(&node.value)?;
                let obj = self.call_ast("Expr", (value,))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Pass(node) => {
                let obj = self.call_ast("Pass", ())?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Break(node) => {
                let obj = self.call_ast("Break", ())?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Continue(node) => {
                let obj = self.call_ast("Continue", ())?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::Delete(node) => {
                let targets = self.expr_list(&node.targets)?;
                let obj = self.call_ast("Delete", (targets,))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Stmt::TypeAlias(_)
            | ast::Stmt::AugAssign(_)
            | ast::Stmt::AsyncFor(_)
            | ast::Stmt::AsyncWith(_)
            | ast::Stmt::Match(_)
            | ast::Stmt::TryStar(_) => Err(unsupported(format!(
                "statement conversion is not implemented for {}",
                stmt_name(stmt)
            ))),
        }
    }

    fn function_def(&mut self, node: &ast::StmtFunctionDef, is_async: bool) -> PyResult<Py<PyAny>> {
        let args = self.arguments(&node.args)?;
        let body = self.stmt_list(&node.body)?;
        let decorators = self.expr_list(&node.decorator_list)?;
        let returns = self.optional_expr(node.returns.as_ref())?;
        let type_comment = match &node.type_comment {
            Some(value) => value.clone().into_pyobject(self.py)?.unbind().into(),
            None => self.none(),
        };
        let type_params = self.list(Vec::new())?;
        let class_name = if is_async {
            "AsyncFunctionDef"
        } else {
            "FunctionDef"
        };
        if !node.type_params.is_empty() {
            return Err(unsupported(
                "non-empty function type_params are not implemented",
            ));
        }
        let obj = self.call_ast(
            class_name,
            (
                node.name.to_string(),
                args,
                body,
                decorators,
                returns,
                type_comment,
                type_params,
            ),
        )?;
        self.set_location(&obj, node.range)?;
        Ok(obj.unbind())
    }

    fn async_function_def(&mut self, node: &ast::StmtAsyncFunctionDef) -> PyResult<Py<PyAny>> {
        let args = self.arguments(&node.args)?;
        let body = self.stmt_list(&node.body)?;
        let decorators = self.expr_list(&node.decorator_list)?;
        let returns = self.optional_expr(node.returns.as_ref())?;
        let type_comment = match &node.type_comment {
            Some(value) => value.clone().into_pyobject(self.py)?.unbind().into(),
            None => self.none(),
        };
        let type_params = self.list(Vec::new())?;
        if !node.type_params.is_empty() {
            return Err(unsupported(
                "non-empty async function type_params are not implemented",
            ));
        }
        let obj = self.call_ast(
            "AsyncFunctionDef",
            (
                node.name.to_string(),
                args,
                body,
                decorators,
                returns,
                type_comment,
                type_params,
            ),
        )?;
        self.set_location(&obj, node.range)?;
        Ok(obj.unbind())
    }

    fn class_def(&mut self, node: &ast::StmtClassDef) -> PyResult<Py<PyAny>> {
        if !node.type_params.is_empty() {
            return Err(unsupported(
                "non-empty class type_params are not implemented",
            ));
        }
        let bases = self.expr_list(&node.bases)?;
        let keywords = self.keyword_list(&node.keywords)?;
        let body = self.stmt_list(&node.body)?;
        let decorators = self.expr_list(&node.decorator_list)?;
        let type_params = self.list(Vec::new())?;
        let obj = self.call_ast(
            "ClassDef",
            (
                node.name.to_string(),
                bases,
                keywords,
                body,
                decorators,
                type_params,
            ),
        )?;
        self.set_location(&obj, node.range)?;
        Ok(obj.unbind())
    }

    fn expr(&mut self, expr: &ast::Expr) -> PyResult<Py<PyAny>> {
        match expr {
            ast::Expr::BoolOp(node) => {
                let op = self.bool_op(node.op)?;
                let values = self.expr_list(&node.values)?;
                let obj = self.call_ast("BoolOp", (op, values))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::BinOp(node) => {
                let left = self.expr(&node.left)?;
                let op = self.operator(node.op)?;
                let right = self.expr(&node.right)?;
                let obj = self.call_ast("BinOp", (left, op, right))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::UnaryOp(node) => {
                let op = self.unary_op(node.op)?;
                let operand = self.expr(&node.operand)?;
                let obj = self.call_ast("UnaryOp", (op, operand))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::IfExp(node) => {
                let test = self.expr(&node.test)?;
                let body = self.expr(&node.body)?;
                let orelse = self.expr(&node.orelse)?;
                let obj = self.call_ast("IfExp", (test, body, orelse))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Dict(node) => {
                let keys = self.optional_expr_list(&node.keys)?;
                let values = self.expr_list(&node.values)?;
                let obj = self.call_ast("Dict", (keys, values))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Set(node) => {
                let elts = self.expr_list(&node.elts)?;
                let obj = self.call_ast("Set", (elts,))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Compare(node) => {
                let left = self.expr(&node.left)?;
                let ops = self.cmp_op_list(&node.ops)?;
                let comparators = self.expr_list(&node.comparators)?;
                let obj = self.call_ast("Compare", (left, ops, comparators))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Call(node) => {
                let func = self.expr(&node.func)?;
                let args = self.expr_list(&node.args)?;
                let keywords = self.keyword_list(&node.keywords)?;
                let obj = self.call_ast("Call", (func, args, keywords))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Constant(node) => {
                let value = self.constant(&node.value)?;
                let kind = match &node.kind {
                    Some(value) => value.clone().into_pyobject(self.py)?.unbind().into(),
                    None => self.none(),
                };
                let obj = self.call_ast("Constant", (value, kind))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Attribute(node) => {
                let value = self.expr(&node.value)?;
                let ctx = self.expr_context(node.ctx)?;
                let obj = self.call_ast("Attribute", (value, node.attr.to_string(), ctx))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Subscript(node) => {
                let value = self.expr(&node.value)?;
                let slice = self.expr(&node.slice)?;
                let ctx = self.expr_context(node.ctx)?;
                let obj = self.call_ast("Subscript", (value, slice, ctx))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Starred(node) => {
                let value = self.expr(&node.value)?;
                let ctx = self.expr_context(node.ctx)?;
                let obj = self.call_ast("Starred", (value, ctx))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Name(node) => {
                let ctx = self.expr_context(node.ctx)?;
                let obj = self.call_ast("Name", (node.id.to_string(), ctx))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::List(node) => {
                let elts = self.expr_list(&node.elts)?;
                let ctx = self.expr_context(node.ctx)?;
                let obj = self.call_ast("List", (elts, ctx))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Tuple(node) => {
                let elts = self.expr_list(&node.elts)?;
                let ctx = self.expr_context(node.ctx)?;
                let obj = self.call_ast("Tuple", (elts, ctx))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::Slice(node) => {
                let lower = self.optional_expr(node.lower.as_ref())?;
                let upper = self.optional_expr(node.upper.as_ref())?;
                let step = self.optional_expr(node.step.as_ref())?;
                let obj = self.call_ast("Slice", (lower, upper, step))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::ListComp(node) => {
                let elt = self.expr(&node.elt)?;
                let generators = self.comprehension_list(&node.generators)?;
                let obj = self.call_ast("ListComp", (elt, generators))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::SetComp(node) => {
                let elt = self.expr(&node.elt)?;
                let generators = self.comprehension_list(&node.generators)?;
                let obj = self.call_ast("SetComp", (elt, generators))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::DictComp(node) => {
                let key = self.expr(&node.key)?;
                let value = self.expr(&node.value)?;
                let generators = self.comprehension_list(&node.generators)?;
                let obj = self.call_ast("DictComp", (key, value, generators))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::GeneratorExp(node) => {
                let elt = self.expr(&node.elt)?;
                let generators = self.comprehension_list(&node.generators)?;
                let obj = self.call_ast("GeneratorExp", (elt, generators))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::FormattedValue(node) => {
                let value = self.expr(&node.value)?;
                let conversion = conversion_flag_to_i32(node.conversion);
                let format_spec = self.optional_expr(node.format_spec.as_ref())?;
                let obj = self.call_ast("FormattedValue", (value, conversion, format_spec))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::JoinedStr(node) => {
                let values = self.expr_list(&node.values)?;
                let obj = self.call_ast("JoinedStr", (values,))?;
                self.set_location(&obj, node.range)?;
                Ok(obj.unbind())
            }
            ast::Expr::NamedExpr(_)
            | ast::Expr::Lambda(_)
            | ast::Expr::Await(_)
            | ast::Expr::Yield(_)
            | ast::Expr::YieldFrom(_) => Err(unsupported(format!(
                "expression conversion is not implemented for {}",
                expr_name(expr)
            ))),
        }
    }

    fn arguments(&mut self, args: &ast::Arguments) -> PyResult<Py<PyAny>> {
        let posonlyargs = self.arg_with_default_defs(&args.posonlyargs)?;
        let normal_args = self.arg_with_default_defs(&args.args)?;
        let vararg = self.optional_arg(args.vararg.as_ref())?;
        let kwonlyargs = self.arg_with_default_defs(&args.kwonlyargs)?;
        let kw_defaults = self.kw_defaults(&args.kwonlyargs)?;
        let kwarg = self.optional_arg(args.kwarg.as_ref())?;
        let defaults = self.positional_defaults(&args.posonlyargs, &args.args)?;
        Ok(self
            .call_ast(
                "arguments",
                (
                    posonlyargs,
                    normal_args,
                    vararg,
                    kwonlyargs,
                    kw_defaults,
                    kwarg,
                    defaults,
                ),
            )?
            .unbind())
    }

    fn arg_with_default_defs(&mut self, args: &[ast::ArgWithDefault]) -> PyResult<Py<PyAny>> {
        let mut items = Vec::with_capacity(args.len());
        for arg in args {
            items.push(self.arg(&arg.def)?);
        }
        self.list(items)
    }

    fn positional_defaults(
        &mut self,
        posonlyargs: &[ast::ArgWithDefault],
        args: &[ast::ArgWithDefault],
    ) -> PyResult<Py<PyAny>> {
        let mut items = Vec::new();
        for arg in posonlyargs.iter().chain(args.iter()) {
            if let Some(default) = &arg.default {
                items.push(self.expr(default)?);
            }
        }
        self.list(items)
    }

    fn kw_defaults(&mut self, args: &[ast::ArgWithDefault]) -> PyResult<Py<PyAny>> {
        let mut items = Vec::with_capacity(args.len());
        for arg in args {
            match &arg.default {
                Some(default) => items.push(self.expr(default)?),
                None => items.push(self.none()),
            }
        }
        self.list(items)
    }

    fn arg(&mut self, arg: &ast::Arg) -> PyResult<Py<PyAny>> {
        let annotation = self.optional_expr(arg.annotation.as_ref())?;
        let type_comment = match &arg.type_comment {
            Some(value) => value.clone().into_pyobject(self.py)?.unbind().into(),
            None => self.none(),
        };
        let obj = self.call_ast("arg", (arg.arg.to_string(), annotation, type_comment))?;
        self.set_location(&obj, arg.range)?;
        Ok(obj.unbind())
    }

    fn keyword_list(&mut self, keywords: &[ast::Keyword]) -> PyResult<Py<PyAny>> {
        let mut items = Vec::with_capacity(keywords.len());
        for keyword in keywords {
            let arg = self.optional_identifier(keyword.arg.as_ref());
            let value = self.expr(&keyword.value)?;
            let obj = self.call_ast("keyword", (arg, value))?;
            self.set_location(&obj, keyword.range)?;
            items.push(obj.unbind());
        }
        self.list(items)
    }

    fn alias_list(&mut self, aliases: &[ast::Alias]) -> PyResult<Py<PyAny>> {
        let mut items = Vec::with_capacity(aliases.len());
        for alias in aliases {
            let asname = self.optional_identifier(alias.asname.as_ref());
            let obj = self.call_ast("alias", (alias.name.to_string(), asname))?;
            self.set_location(&obj, alias.range)?;
            items.push(obj.unbind());
        }
        self.list(items)
    }

    fn with_item_list(&mut self, items: &[ast::WithItem]) -> PyResult<Py<PyAny>> {
        let mut converted = Vec::with_capacity(items.len());
        for item in items {
            let context_expr = self.expr(&item.context_expr)?;
            let optional_vars = match &item.optional_vars {
                Some(expr) => self.expr(expr)?,
                None => self.none(),
            };
            converted.push(
                self.call_ast("withitem", (context_expr, optional_vars))?
                    .unbind(),
            );
        }
        self.list(converted)
    }

    fn comprehension_list(&mut self, comprehensions: &[ast::Comprehension]) -> PyResult<Py<PyAny>> {
        let mut converted = Vec::with_capacity(comprehensions.len());
        for comprehension in comprehensions {
            let target = self.expr(&comprehension.target)?;
            let iter = self.expr(&comprehension.iter)?;
            let ifs = self.expr_list(&comprehension.ifs)?;
            let is_async = if comprehension.is_async { 1 } else { 0 };
            converted.push(
                self.call_ast("comprehension", (target, iter, ifs, is_async))?
                    .unbind(),
            );
        }
        self.list(converted)
    }

    fn except_handler_list(&mut self, handlers: &[ast::ExceptHandler]) -> PyResult<Py<PyAny>> {
        let mut converted = Vec::with_capacity(handlers.len());
        for handler in handlers {
            match handler {
                ast::ExceptHandler::ExceptHandler(node) => {
                    let type_ = self.optional_expr(node.type_.as_ref())?;
                    let name = self.optional_identifier(node.name.as_ref());
                    let body = self.stmt_list(&node.body)?;
                    let obj = self.call_ast("ExceptHandler", (type_, name, body))?;
                    self.set_location(&obj, node.range)?;
                    converted.push(obj.unbind());
                }
            }
        }
        self.list(converted)
    }

    fn type_ignore_list(&mut self, type_ignores: &[ast::TypeIgnore]) -> PyResult<Py<PyAny>> {
        let mut converted = Vec::with_capacity(type_ignores.len());
        for type_ignore in type_ignores {
            match type_ignore {
                ast::TypeIgnore::TypeIgnore(node) => {
                    converted.push(
                        self.call_ast("TypeIgnore", (node.lineno.to_u32(), node.tag.clone()))?
                            .unbind(),
                    );
                }
            }
        }
        self.list(converted)
    }

    fn expr_context(&mut self, ctx: ast::ExprContext) -> PyResult<Py<PyAny>> {
        match ctx {
            ast::ExprContext::Load => self.simple("Load"),
            ast::ExprContext::Store => self.simple("Store"),
            ast::ExprContext::Del => self.simple("Del"),
        }
    }

    fn bool_op(&mut self, op: ast::BoolOp) -> PyResult<Py<PyAny>> {
        match op {
            ast::BoolOp::And => self.simple("And"),
            ast::BoolOp::Or => self.simple("Or"),
        }
    }

    fn operator(&mut self, op: ast::Operator) -> PyResult<Py<PyAny>> {
        let name = match op {
            ast::Operator::Add => "Add",
            ast::Operator::Sub => "Sub",
            ast::Operator::Mult => "Mult",
            ast::Operator::MatMult => "MatMult",
            ast::Operator::Div => "Div",
            ast::Operator::Mod => "Mod",
            ast::Operator::Pow => "Pow",
            ast::Operator::LShift => "LShift",
            ast::Operator::RShift => "RShift",
            ast::Operator::BitOr => "BitOr",
            ast::Operator::BitXor => "BitXor",
            ast::Operator::BitAnd => "BitAnd",
            ast::Operator::FloorDiv => "FloorDiv",
        };
        self.simple(name)
    }

    fn unary_op(&mut self, op: ast::UnaryOp) -> PyResult<Py<PyAny>> {
        let name = match op {
            ast::UnaryOp::Invert => "Invert",
            ast::UnaryOp::Not => "Not",
            ast::UnaryOp::UAdd => "UAdd",
            ast::UnaryOp::USub => "USub",
        };
        self.simple(name)
    }

    fn cmp_op_list(&mut self, ops: &[ast::CmpOp]) -> PyResult<Py<PyAny>> {
        let mut converted = Vec::with_capacity(ops.len());
        for op in ops {
            let name = match op {
                ast::CmpOp::Eq => "Eq",
                ast::CmpOp::NotEq => "NotEq",
                ast::CmpOp::Lt => "Lt",
                ast::CmpOp::LtE => "LtE",
                ast::CmpOp::Gt => "Gt",
                ast::CmpOp::GtE => "GtE",
                ast::CmpOp::Is => "Is",
                ast::CmpOp::IsNot => "IsNot",
                ast::CmpOp::In => "In",
                ast::CmpOp::NotIn => "NotIn",
            };
            converted.push(self.simple(name)?);
        }
        self.list(converted)
    }

    fn constant(&mut self, value: &ast::Constant) -> PyResult<Py<PyAny>> {
        match value {
            ast::Constant::None => Ok(self.none()),
            ast::Constant::Bool(value) => {
                let builtins = self.py.import("builtins")?;
                Ok(builtins.getattr("bool")?.call1((*value,))?.unbind())
            }
            ast::Constant::Str(value) => Ok(value.clone().into_pyobject(self.py)?.unbind().into()),
            ast::Constant::Bytes(value) => Ok(PyBytes::new(self.py, value).into_any().unbind()),
            ast::Constant::Int(value) => {
                let builtins = self.py.import("builtins")?;
                Ok(builtins
                    .getattr("int")?
                    .call1((value.to_string(),))?
                    .unbind())
            }
            ast::Constant::Tuple(values) => {
                let mut items = Vec::with_capacity(values.len());
                for value in values {
                    items.push(self.constant(value)?);
                }
                let tuple_ctor = self.py.import("builtins")?.getattr("tuple")?;
                let list = self.list(items)?;
                Ok(tuple_ctor.call1((list,))?.unbind())
            }
            ast::Constant::Float(value) => Ok(value.into_pyobject(self.py)?.unbind().into()),
            ast::Constant::Complex { real, imag } => {
                let builtins = self.py.import("builtins")?;
                Ok(builtins.getattr("complex")?.call1((*real, *imag))?.unbind())
            }
            ast::Constant::Ellipsis => Ok(self.py.Ellipsis()),
        }
    }
}

fn dict_from_counts(py: Python<'_>, counts: &BTreeMap<String, usize>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);
    for (key, value) in counts {
        dict.set_item(key, value)?;
    }
    Ok(dict.unbind())
}

fn bump(counts: &mut BTreeMap<String, usize>, name: &str) {
    *counts.entry(name.to_string()).or_insert(0) += 1;
}

fn count_module(module: &ast::ModModule) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    bump(&mut counts, "Module");
    for stmt in &module.body {
        count_stmt(stmt, &mut counts);
    }
    for type_ignore in &module.type_ignores {
        match type_ignore {
            ast::TypeIgnore::TypeIgnore(_) => bump(&mut counts, "TypeIgnore"),
        }
    }
    counts
}

fn count_stmt(stmt: &ast::Stmt, counts: &mut BTreeMap<String, usize>) {
    bump(counts, stmt_name(stmt));
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            count_arguments(&node.args, counts);
            count_exprs(&node.decorator_list, counts);
            if let Some(value) = &node.returns {
                count_expr(value, counts);
            }
            count_stmts(&node.body, counts);
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            count_arguments(&node.args, counts);
            count_exprs(&node.decorator_list, counts);
            if let Some(value) = &node.returns {
                count_expr(value, counts);
            }
            count_stmts(&node.body, counts);
        }
        ast::Stmt::ClassDef(node) => {
            count_exprs(&node.bases, counts);
            for keyword in &node.keywords {
                bump(counts, "keyword");
                count_expr(&keyword.value, counts);
            }
            count_exprs(&node.decorator_list, counts);
            count_stmts(&node.body, counts);
        }
        ast::Stmt::Return(node) => {
            if let Some(value) = &node.value {
                count_expr(value, counts);
            }
        }
        ast::Stmt::Delete(node) => count_exprs(&node.targets, counts),
        ast::Stmt::Assign(node) => {
            count_exprs(&node.targets, counts);
            count_expr(&node.value, counts);
        }
        ast::Stmt::TypeAlias(node) => {
            count_expr(&node.name, counts);
            count_expr(&node.value, counts);
        }
        ast::Stmt::AugAssign(node) => {
            count_expr(&node.target, counts);
            count_expr(&node.value, counts);
        }
        ast::Stmt::AnnAssign(node) => {
            count_expr(&node.target, counts);
            count_expr(&node.annotation, counts);
            if let Some(value) = &node.value {
                count_expr(value, counts);
            }
        }
        ast::Stmt::For(node) => {
            count_expr(&node.target, counts);
            count_expr(&node.iter, counts);
            count_stmts(&node.body, counts);
            count_stmts(&node.orelse, counts);
        }
        ast::Stmt::AsyncFor(node) => {
            count_expr(&node.target, counts);
            count_expr(&node.iter, counts);
            count_stmts(&node.body, counts);
            count_stmts(&node.orelse, counts);
        }
        ast::Stmt::While(node) => {
            count_expr(&node.test, counts);
            count_stmts(&node.body, counts);
            count_stmts(&node.orelse, counts);
        }
        ast::Stmt::If(node) => {
            count_expr(&node.test, counts);
            count_stmts(&node.body, counts);
            count_stmts(&node.orelse, counts);
        }
        ast::Stmt::With(node) => {
            for item in &node.items {
                bump(counts, "withitem");
                count_expr(&item.context_expr, counts);
                if let Some(value) = &item.optional_vars {
                    count_expr(value, counts);
                }
            }
            count_stmts(&node.body, counts);
        }
        ast::Stmt::AsyncWith(node) => {
            for item in &node.items {
                bump(counts, "withitem");
                count_expr(&item.context_expr, counts);
                if let Some(value) = &item.optional_vars {
                    count_expr(value, counts);
                }
            }
            count_stmts(&node.body, counts);
        }
        ast::Stmt::Match(node) => {
            count_expr(&node.subject, counts);
            for case in &node.cases {
                bump(counts, "match_case");
                if let Some(guard) = &case.guard {
                    count_expr(guard, counts);
                }
                count_stmts(&case.body, counts);
            }
        }
        ast::Stmt::Raise(node) => {
            if let Some(value) = &node.exc {
                count_expr(value, counts);
            }
            if let Some(value) = &node.cause {
                count_expr(value, counts);
            }
        }
        ast::Stmt::Try(node) => {
            count_stmts(&node.body, counts);
            for handler in &node.handlers {
                count_except_handler(handler, counts);
            }
            count_stmts(&node.orelse, counts);
            count_stmts(&node.finalbody, counts);
        }
        ast::Stmt::TryStar(node) => {
            count_stmts(&node.body, counts);
            for handler in &node.handlers {
                count_except_handler(handler, counts);
            }
            count_stmts(&node.orelse, counts);
            count_stmts(&node.finalbody, counts);
        }
        ast::Stmt::Assert(node) => {
            count_expr(&node.test, counts);
            if let Some(value) = &node.msg {
                count_expr(value, counts);
            }
        }
        ast::Stmt::Import(node) => {
            for _ in &node.names {
                bump(counts, "alias");
            }
        }
        ast::Stmt::ImportFrom(node) => {
            for _ in &node.names {
                bump(counts, "alias");
            }
        }
        ast::Stmt::Expr(node) => count_expr(&node.value, counts),
        ast::Stmt::Global(_)
        | ast::Stmt::Nonlocal(_)
        | ast::Stmt::Pass(_)
        | ast::Stmt::Break(_)
        | ast::Stmt::Continue(_) => {}
    }
}

fn count_stmts(stmts: &[ast::Stmt], counts: &mut BTreeMap<String, usize>) {
    for stmt in stmts {
        count_stmt(stmt, counts);
    }
}

fn count_exprs(exprs: &[ast::Expr], counts: &mut BTreeMap<String, usize>) {
    for expr in exprs {
        count_expr(expr, counts);
    }
}

fn count_expr(expr: &ast::Expr, counts: &mut BTreeMap<String, usize>) {
    bump(counts, expr_name(expr));
    match expr {
        ast::Expr::BoolOp(node) => count_exprs(&node.values, counts),
        ast::Expr::NamedExpr(node) => {
            count_expr(&node.target, counts);
            count_expr(&node.value, counts);
        }
        ast::Expr::BinOp(node) => {
            count_expr(&node.left, counts);
            count_expr(&node.right, counts);
        }
        ast::Expr::UnaryOp(node) => count_expr(&node.operand, counts),
        ast::Expr::Lambda(node) => {
            count_arguments(&node.args, counts);
            count_expr(&node.body, counts);
        }
        ast::Expr::IfExp(node) => {
            count_expr(&node.test, counts);
            count_expr(&node.body, counts);
            count_expr(&node.orelse, counts);
        }
        ast::Expr::Dict(node) => {
            for expr in node.keys.iter().flatten() {
                count_expr(expr, counts);
            }
            count_exprs(&node.values, counts);
        }
        ast::Expr::Set(node) => count_exprs(&node.elts, counts),
        ast::Expr::ListComp(node) => {
            count_expr(&node.elt, counts);
            count_comprehensions(&node.generators, counts);
        }
        ast::Expr::SetComp(node) => {
            count_expr(&node.elt, counts);
            count_comprehensions(&node.generators, counts);
        }
        ast::Expr::DictComp(node) => {
            count_expr(&node.key, counts);
            count_expr(&node.value, counts);
            count_comprehensions(&node.generators, counts);
        }
        ast::Expr::GeneratorExp(node) => {
            count_expr(&node.elt, counts);
            count_comprehensions(&node.generators, counts);
        }
        ast::Expr::Await(node) => count_expr(&node.value, counts),
        ast::Expr::Yield(node) => {
            if let Some(value) = &node.value {
                count_expr(value, counts);
            }
        }
        ast::Expr::YieldFrom(node) => count_expr(&node.value, counts),
        ast::Expr::Compare(node) => {
            count_expr(&node.left, counts);
            count_exprs(&node.comparators, counts);
        }
        ast::Expr::Call(node) => {
            count_expr(&node.func, counts);
            count_exprs(&node.args, counts);
            for keyword in &node.keywords {
                bump(counts, "keyword");
                count_expr(&keyword.value, counts);
            }
        }
        ast::Expr::FormattedValue(node) => {
            count_expr(&node.value, counts);
            if let Some(value) = &node.format_spec {
                count_expr(value, counts);
            }
        }
        ast::Expr::JoinedStr(node) => count_exprs(&node.values, counts),
        ast::Expr::Attribute(node) => count_expr(&node.value, counts),
        ast::Expr::Subscript(node) => {
            count_expr(&node.value, counts);
            count_expr(&node.slice, counts);
        }
        ast::Expr::Starred(node) => count_expr(&node.value, counts),
        ast::Expr::List(node) => count_exprs(&node.elts, counts),
        ast::Expr::Tuple(node) => count_exprs(&node.elts, counts),
        ast::Expr::Slice(node) => {
            if let Some(value) = &node.lower {
                count_expr(value, counts);
            }
            if let Some(value) = &node.upper {
                count_expr(value, counts);
            }
            if let Some(value) = &node.step {
                count_expr(value, counts);
            }
        }
        ast::Expr::Constant(_) | ast::Expr::Name(_) => {}
    }
}

fn count_arguments(args: &ast::Arguments, counts: &mut BTreeMap<String, usize>) {
    bump(counts, "arguments");
    for arg in args
        .posonlyargs
        .iter()
        .chain(args.args.iter())
        .chain(args.kwonlyargs.iter())
    {
        bump(counts, "arg");
        if let Some(annotation) = &arg.def.annotation {
            count_expr(annotation, counts);
        }
        if let Some(default) = &arg.default {
            count_expr(default, counts);
        }
    }
    if let Some(arg) = &args.vararg {
        bump(counts, "arg");
        if let Some(annotation) = &arg.annotation {
            count_expr(annotation, counts);
        }
    }
    if let Some(arg) = &args.kwarg {
        bump(counts, "arg");
        if let Some(annotation) = &arg.annotation {
            count_expr(annotation, counts);
        }
    }
}

fn count_comprehensions(
    comprehensions: &[ast::Comprehension],
    counts: &mut BTreeMap<String, usize>,
) {
    for comprehension in comprehensions {
        bump(counts, "comprehension");
        count_expr(&comprehension.target, counts);
        count_expr(&comprehension.iter, counts);
        count_exprs(&comprehension.ifs, counts);
    }
}

fn count_except_handler(handler: &ast::ExceptHandler, counts: &mut BTreeMap<String, usize>) {
    match handler {
        ast::ExceptHandler::ExceptHandler(node) => {
            bump(counts, "ExceptHandler");
            if let Some(type_) = &node.type_ {
                count_expr(type_, counts);
            }
            count_stmts(&node.body, counts);
        }
    }
}

fn stmt_name(stmt: &ast::Stmt) -> &'static str {
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

fn expr_name(expr: &ast::Expr) -> &'static str {
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
        ast::Expr::DictComp(_) => "DictComp",
        ast::Expr::GeneratorExp(_) => "GeneratorExp",
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

fn conversion_flag_to_i32(flag: ast::ConversionFlag) -> i32 {
    match flag {
        ast::ConversionFlag::None => -1,
        ast::ConversionFlag::Str => b's' as i32,
        ast::ConversionFlag::Ascii => b'a' as i32,
        ast::ConversionFlag::Repr => b'r' as i32,
    }
}
