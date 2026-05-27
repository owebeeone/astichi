use std::collections::{BTreeMap, BTreeSet};

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule, PyTuple};
use rustpython_parser::ast;

use crate::handles::EngineHandle;
use crate::occurrence_store::NativeTemplateHandle;

const PACKAGE_SCHEMA: &str = "astichi.lower-template-package.v2";
const ARG_SUFFIX: &str = "__astichi_arg__";
const KEEP_SUFFIX: &str = "__astichi_keep__";
const PARAM_HOLE_SUFFIX: &str = "__astichi_param_hole__";

#[derive(Clone)]
struct ScopeSpec {
    scope_id: usize,
    parent_scope_id: Option<usize>,
    scope_kind: String,
    ast_path: String,
    owner_path: Vec<String>,
    local_bindings: Vec<String>,
    arguments: Vec<String>,
    start_line: Option<u32>,
}

#[derive(Clone)]
pub(crate) struct PackageBuilder {
    pub(crate) strings: Vec<String>,
    string_index: BTreeMap<String, usize>,
    pub(crate) paths: Vec<Vec<String>>,
    path_index: BTreeMap<Vec<String>, usize>,
    pub(crate) ast_paths: Vec<String>,
    ast_path_index: BTreeMap<String, usize>,
    binding_sets: Vec<(usize, Vec<usize>)>,
    binding_set_index: BTreeMap<Vec<String>, usize>,
    pub(crate) locators: Vec<LocatorRow>,
    pub(crate) records: Vec<RecordRow>,
    scopes: Vec<ScopeRow>,
    markers: Vec<MarkerRow>,
    pyimport_markers: Vec<PyImportMarkerRow>,
    managed_imports: Vec<ManagedImportRow>,
    comment_markers: Vec<CommentMarkerRow>,
    ref_markers: Vec<RefMarkerRow>,
    unroll_markers: Vec<UnrollMarkerRow>,
}

pub(crate) struct PackageMarkerHygieneSpec {
    pub(crate) source_name: String,
    pub(crate) resource_name: String,
    pub(crate) scope_id: usize,
}

pub(crate) struct ManagedImportHygieneSpec {
    pub(crate) final_local_name: String,
    pub(crate) module_path: Vec<String>,
    pub(crate) original_symbol: Option<String>,
}

pub(crate) struct BuiltPackage {
    pub(crate) package: PackageBuilder,
    pub(crate) module: ast::ModModule,
}

#[derive(Clone)]
pub(crate) struct LocatorRow {
    pub(crate) locator_id: usize,
    pub(crate) ast_path_id: usize,
    pub(crate) role_key_id: usize,
    pub(crate) parent_locator_id: Option<usize>,
    pub(crate) authored_summary_id: usize,
    pub(crate) materialization_anchor_id: usize,
}

#[derive(Clone)]
pub(crate) struct RecordRow {
    pub(crate) template_record_id: usize,
    pub(crate) surface_key_id: usize,
    pub(crate) locator_id: usize,
    pub(crate) resource_name_id: Option<usize>,
    pub(crate) inventory_kind_id: usize,
    pub(crate) owner_path_id: usize,
    pub(crate) semantic_summary_id: usize,
}

#[derive(Clone)]
struct ScopeRow {
    scope_id: usize,
    parent_scope_id: Option<usize>,
    scope_kind_id: usize,
    ast_path_id: usize,
    owner_path_id: usize,
    local_binding_set_id: usize,
    argument_set_id: usize,
    start_line: Option<u32>,
}

#[derive(Clone)]
struct MarkerRow {
    marker_id: usize,
    source_order: usize,
    marker_kind_id: usize,
    source_name_id: usize,
    operation_key_id: usize,
    scope_id: usize,
    owner_path_id: usize,
    ast_path_id: usize,
    statement_path_id: Option<usize>,
    resource_name_id: Option<usize>,
    flags: Vec<String>,
}

#[derive(Clone)]
struct PyImportMarkerRow {
    pyimport_marker_id: usize,
    marker_id: usize,
    module_path_id: Option<usize>,
    name_ids: Vec<usize>,
    as_name_id: Option<usize>,
    flags: Vec<String>,
}

#[derive(Clone)]
struct ManagedImportRow {
    managed_import_id: usize,
    marker_id: usize,
    source_order: usize,
    scope_id: usize,
    module_path_id: Option<usize>,
    final_local_name_id: usize,
    original_symbol_id: Option<usize>,
    flags: Vec<String>,
}

#[derive(Clone)]
struct CommentMarkerRow {
    comment_marker_id: usize,
    marker_id: usize,
    payload_id: usize,
    flags: Vec<String>,
}

#[derive(Clone)]
struct RefMarkerRow {
    ref_marker_id: usize,
    marker_id: usize,
    ref_kind_id: usize,
    context_id: usize,
    sentinel_attr_id: Option<usize>,
    literal_path_id: Option<usize>,
    flags: Vec<String>,
}

#[derive(Clone)]
struct UnrollMarkerRow {
    unroll_marker_id: usize,
    marker_id: usize,
    statement_path_id: usize,
    target_ast_path_id: usize,
    iter_ast_path_id: usize,
    domain_ast_path_id: usize,
    body_path_id: usize,
    orelse_path_id: Option<usize>,
    target_binding_set_id: usize,
    domain_shape_id: usize,
    flags: Vec<String>,
}

#[pyfunction(name = "extract_template_package_v2_snapshot")]
#[pyo3(signature = (engine, source, filename = None, line_number = 1))]
fn extract_template_package_v2_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    source: String,
    filename: Option<String>,
    line_number: u32,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    let built = build_package(py, &engine, source, filename, line_number)?;
    built.package.snapshot(py)
}

#[pyfunction(name = "register_template_package_v2_source")]
#[pyo3(signature = (engine, source, filename = None, line_number = 1))]
fn register_template_package_v2_source(
    py: Python<'_>,
    engine: PyRefMut<'_, EngineHandle>,
    source: String,
    filename: Option<String>,
    line_number: u32,
) -> PyResult<NativeTemplateHandle> {
    engine.ensure_open()?;
    let built = build_package(py, &engine, source, filename, line_number)?;
    crate::occurrence_store::register_template_package(engine, built.package, Some(built.module))
}

#[pyfunction(name = "template_package_v2_snapshot")]
fn template_package_v2_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    template: PyRef<'_, NativeTemplateHandle>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    crate::occurrence_store::template_package_v2_snapshot(py, engine, template)
}

fn build_package(
    py: Python<'_>,
    engine: &EngineHandle,
    source: String,
    filename: Option<String>,
    line_number: u32,
) -> PyResult<BuiltPackage> {
    let surface_bundle = engine
        .surface_bundle()
        .ok_or_else(|| crate::errors::schema_error("surface bundle has not been registered"))?;
    let filename = filename.unwrap_or_else(|| "<astichi-native>".to_string());
    let module = crate::template_extract::validate_compile_module(&source, &filename)?;
    let records = crate::template_extract::extract_template_records(&source, &module, line_number)?;
    let source_summary = format!("compile line={line_number} records={}", records.len());
    let template_key =
        crate::template_extract::native_template_key(py, &source, &module, &source_summary)?;

    let mut package = PackageBuilder::new(
        surface_bundle.bundle_signature(),
        &template_key,
        &source_summary,
    );
    for (index, record) in records.iter().enumerate() {
        package.add_locator(
            index,
            &record.ast_path,
            &record.role_key,
            &record.authored_summary,
            &record.materialization_anchor,
        );
        package.add_record(
            index,
            &record.surface_key,
            index,
            &record.resource_name,
            &record.inventory_kind,
            &record.code_owner,
            &record.semantic_summary,
        );
    }
    let source_map = crate::template_extract::SourceMap::new(&source);
    let scopes = extract_scopes(&module, &source_map, line_number);
    for scope in &scopes {
        package.add_scope(scope);
    }
    let mut marker_state = MarkerState::new();
    for (index, stmt) in module.body.iter().enumerate() {
        visit_stmt_markers(
            stmt,
            &format!("body[{index}]"),
            &scopes,
            &mut package,
            &mut marker_state,
        )?;
    }
    for pending in marker_state.pending_pyimports {
        package.add_pyimport_marker(
            pending.marker_id,
            pending.source_order,
            pending.scope_id,
            pending.module_path,
            pending.names,
            pending.as_name,
            pending.flags,
        );
    }
    for pending in marker_state.pending_comments {
        package.add_comment_marker(pending.marker_id, &pending.payload);
    }
    for (index, stmt) in module.body.iter().enumerate() {
        extract_typed_marker_rows_stmt(stmt, &format!("body[{index}]"), &mut package)?;
    }
    Ok(BuiltPackage { package, module })
}

fn py_optional_string(py: Python<'_>, value: Option<&str>) -> PyResult<Py<PyAny>> {
    match value {
        Some(text) => Ok(text.into_pyobject(py)?.into_any().unbind()),
        None => Ok(py.None()),
    }
}

fn py_path_tuple(py: Python<'_>, parts: &[String]) -> PyResult<Py<PyAny>> {
    Ok(PyTuple::new(py, parts.iter().map(|part| part.as_str()))?
        .into_any()
        .unbind())
}

fn py_string_tuple(py: Python<'_>, values: Vec<&str>) -> PyResult<Py<PyAny>> {
    Ok(PyTuple::new(py, values)?.into_any().unbind())
}

impl PackageBuilder {
    pub(crate) fn hydrate_python_package<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let module = PyModule::import(py, "astichi.lower_engine.package_v2")?;
        let cls = module.getattr("LowerTemplatePackageV2")?;
        let template_key = self
            .strings
            .get(1)
            .ok_or_else(|| crate::errors::schema_error("package is missing template_key"))?;
        let source_summary = self
            .strings
            .get(2)
            .ok_or_else(|| crate::errors::schema_error("package is missing source_summary"))?;
        let surface_bundle_signature = self.strings.first().ok_or_else(|| {
            crate::errors::schema_error("package is missing surface_bundle_signature")
        })?;
        let ctor_kwargs = PyDict::new(py);
        ctor_kwargs.set_item("template_key", template_key)?;
        ctor_kwargs.set_item("source_summary", source_summary)?;
        ctor_kwargs.set_item("surface_bundle_signature", surface_bundle_signature)?;
        let instance = cls.call((), Some(&ctor_kwargs))?;

        for row in &self.locators {
            let kwargs = PyDict::new(py);
            kwargs.set_item("ast_path", self.ast_paths[row.ast_path_id].as_str())?;
            kwargs.set_item("role_key", self.strings[row.role_key_id].as_str())?;
            kwargs.set_item(
                "authored_summary",
                self.strings[row.authored_summary_id].as_str(),
            )?;
            kwargs.set_item(
                "materialization_anchor",
                self.strings[row.materialization_anchor_id].as_str(),
            )?;
            kwargs.set_item("parent_locator_id", row.parent_locator_id)?;
            kwargs.set_item("locator_id", row.locator_id)?;
            instance.call_method("add_locator", (), Some(&kwargs))?;
        }

        for row in &self.records {
            let kwargs = PyDict::new(py);
            kwargs.set_item("surface_key", self.strings[row.surface_key_id].as_str())?;
            kwargs.set_item("locator_id", row.locator_id)?;
            kwargs.set_item("inventory_kind", self.strings[row.inventory_kind_id].as_str())?;
            kwargs.set_item(
                "owner_path",
                py_path_tuple(py, &self.paths[row.owner_path_id])?,
            )?;
            kwargs.set_item(
                "semantic_summary",
                self.strings[row.semantic_summary_id].as_str(),
            )?;
            kwargs.set_item(
                "resource_name",
                row.resource_name_id
                    .map(|id| self.strings[id].as_str())
                    .unwrap_or(""),
            )?;
            kwargs.set_item("template_record_id", row.template_record_id)?;
            instance.call_method("add_record", (), Some(&kwargs))?;
        }

        for row in &self.scopes {
            let kwargs = PyDict::new(py);
            kwargs.set_item("scope_kind", self.strings[row.scope_kind_id].as_str())?;
            kwargs.set_item("ast_path", self.ast_paths[row.ast_path_id].as_str())?;
            kwargs.set_item(
                "owner_path",
                py_path_tuple(py, &self.paths[row.owner_path_id])?,
            )?;
            kwargs.set_item(
                "local_bindings",
                py_string_tuple(py, self.binding_set_names(row.local_binding_set_id))?,
            )?;
            kwargs.set_item(
                "arguments",
                py_string_tuple(py, self.binding_set_names(row.argument_set_id))?,
            )?;
            kwargs.set_item("parent_scope_id", row.parent_scope_id)?;
            kwargs.set_item("start_line", row.start_line)?;
            instance.call_method("add_scope", (), Some(&kwargs))?;
        }

        for row in &self.markers {
            let kwargs = PyDict::new(py);
            kwargs.set_item("marker_kind", self.strings[row.marker_kind_id].as_str())?;
            kwargs.set_item("source_name", self.strings[row.source_name_id].as_str())?;
            kwargs.set_item("ast_path", self.ast_paths[row.ast_path_id].as_str())?;
            match row.statement_path_id {
                Some(id) => kwargs.set_item("statement_path", self.ast_paths[id].as_str())?,
                None => kwargs.set_item("statement_path", py.None())?,
            };
            kwargs.set_item(
                "owner_path",
                py_path_tuple(py, &self.paths[row.owner_path_id])?,
            )?;
            kwargs.set_item("scope_id", row.scope_id)?;
            kwargs.set_item("source_order", row.source_order)?;
            kwargs.set_item(
                "resource_name",
                row.resource_name_id
                    .map(|id| self.strings[id].as_str())
                    .unwrap_or(""),
            )?;
            kwargs.set_item("operation_key", self.strings[row.operation_key_id].as_str())?;
            kwargs.set_item(
                "flags",
                py_string_tuple(
                    py,
                    row.flags.iter().map(|flag| flag.as_str()).collect(),
                )?,
            )?;
            instance.call_method("add_marker", (), Some(&kwargs))?;
        }

        for row in &self.pyimport_markers {
            let kwargs = PyDict::new(py);
            kwargs.set_item("marker_id", row.marker_id)?;
            match row.module_path_id {
                Some(id) => {
                    kwargs.set_item("module_path", py_path_tuple(py, &self.paths[id])?)?
                }
                None => kwargs.set_item("module_path", py.None())?,
            };
            kwargs.set_item(
                "names",
                py_string_tuple(py, self.strings_for_ids(&row.name_ids))?,
            )?;
            kwargs.set_item(
                "as_name",
                row.as_name_id
                    .map(|id| self.strings[id].as_str())
                    .unwrap_or(""),
            )?;
            kwargs.set_item(
                "flags",
                py_string_tuple(
                    py,
                    row.flags.iter().map(|flag| flag.as_str()).collect(),
                )?,
            )?;
            instance.call_method("add_pyimport_marker", (), Some(&kwargs))?;
        }

        for row in &self.comment_markers {
            let kwargs = PyDict::new(py);
            kwargs.set_item("marker_id", row.marker_id)?;
            kwargs.set_item("payload", self.strings[row.payload_id].as_str())?;
            kwargs.set_item(
                "flags",
                py_string_tuple(
                    py,
                    row.flags.iter().map(|flag| flag.as_str()).collect(),
                )?,
            )?;
            instance.call_method("add_comment_marker", (), Some(&kwargs))?;
        }

        for row in &self.ref_markers {
            let kwargs = PyDict::new(py);
            kwargs.set_item("marker_id", row.marker_id)?;
            kwargs.set_item("ref_kind", self.strings[row.ref_kind_id].as_str())?;
            kwargs.set_item("context", self.strings[row.context_id].as_str())?;
            kwargs.set_item(
                "sentinel_attr",
                py_optional_string(
                    py,
                    row.sentinel_attr_id
                        .map(|id| self.strings[id].as_str()),
                )?,
            )?;
            match row.literal_path_id {
                Some(id) => {
                    kwargs.set_item("literal_path", py_path_tuple(py, &self.paths[id])?)?
                }
                None => kwargs.set_item("literal_path", py.None())?,
            };
            kwargs.set_item(
                "flags",
                py_string_tuple(
                    py,
                    row.flags.iter().map(|flag| flag.as_str()).collect(),
                )?,
            )?;
            instance.call_method("add_ref_marker", (), Some(&kwargs))?;
        }

        for row in &self.unroll_markers {
            let kwargs = PyDict::new(py);
            kwargs.set_item("marker_id", row.marker_id)?;
            kwargs.set_item("statement_path", self.ast_paths[row.statement_path_id].as_str())?;
            kwargs.set_item("target_ast_path", self.ast_paths[row.target_ast_path_id].as_str())?;
            kwargs.set_item("iter_ast_path", self.ast_paths[row.iter_ast_path_id].as_str())?;
            kwargs.set_item("domain_ast_path", self.ast_paths[row.domain_ast_path_id].as_str())?;
            kwargs.set_item("body_path", self.ast_paths[row.body_path_id].as_str())?;
            match row.orelse_path_id {
                Some(id) => kwargs.set_item("orelse_path", self.ast_paths[id].as_str())?,
                None => kwargs.set_item("orelse_path", py.None())?,
            };
            kwargs.set_item(
                "target_bindings",
                py_string_tuple(py, self.binding_set_names(row.target_binding_set_id))?,
            )?;
            kwargs.set_item("domain_shape", self.strings[row.domain_shape_id].as_str())?;
            kwargs.set_item(
                "flags",
                py_string_tuple(
                    py,
                    row.flags.iter().map(|flag| flag.as_str()).collect(),
                )?,
            )?;
            instance.call_method("add_unroll_marker", (), Some(&kwargs))?;
        }

        Ok(instance)
    }
}

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_template_package_v2_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(register_template_package_v2_source, m)?)?;
    m.add_function(wrap_pyfunction!(template_package_v2_snapshot, m)?)?;
    Ok(())
}

impl PackageBuilder {
    fn new(surface_bundle_signature: &str, template_key: &str, source_summary: &str) -> Self {
        let mut package = Self {
            strings: Vec::new(),
            string_index: BTreeMap::new(),
            paths: Vec::new(),
            path_index: BTreeMap::new(),
            ast_paths: Vec::new(),
            ast_path_index: BTreeMap::new(),
            binding_sets: Vec::new(),
            binding_set_index: BTreeMap::new(),
            locators: Vec::new(),
            records: Vec::new(),
            scopes: Vec::new(),
            markers: Vec::new(),
            pyimport_markers: Vec::new(),
            managed_imports: Vec::new(),
            comment_markers: Vec::new(),
            ref_markers: Vec::new(),
            unroll_markers: Vec::new(),
        };
        package.intern_string(surface_bundle_signature);
        package.intern_string(template_key);
        package.intern_string(source_summary);
        package
    }

    fn intern_string(&mut self, value: &str) -> usize {
        if let Some(existing) = self.string_index.get(value) {
            return *existing;
        }
        let string_id = self.strings.len();
        self.strings.push(value.to_string());
        self.string_index.insert(value.to_string(), string_id);
        string_id
    }

    fn intern_path(&mut self, parts: &[String]) -> usize {
        if let Some(existing) = self.path_index.get(parts) {
            return *existing;
        }
        for part in parts {
            self.intern_string(part);
        }
        let path_id = self.paths.len();
        let owned = parts.to_vec();
        self.paths.push(owned.clone());
        self.path_index.insert(owned, path_id);
        path_id
    }

    fn intern_ast_path(&mut self, ast_path: &str) -> usize {
        if let Some(existing) = self.ast_path_index.get(ast_path) {
            return *existing;
        }
        let ast_path_id = self.ast_paths.len();
        self.ast_paths.push(ast_path.to_string());
        self.ast_path_index
            .insert(ast_path.to_string(), ast_path_id);
        ast_path_id
    }

    fn intern_binding_set(&mut self, names: &[String]) -> usize {
        let canonical = sorted_unique(names);
        if let Some(existing) = self.binding_set_index.get(&canonical) {
            return *existing;
        }
        let name_ids = canonical
            .iter()
            .map(|name| self.intern_string(name))
            .collect::<Vec<_>>();
        let binding_set_id = self.binding_sets.len();
        self.binding_sets.push((binding_set_id, name_ids));
        self.binding_set_index.insert(canonical, binding_set_id);
        binding_set_id
    }

    fn add_locator(
        &mut self,
        locator_id: usize,
        ast_path: &str,
        role_key: &str,
        authored_summary: &str,
        materialization_anchor: &str,
    ) {
        let ast_path_id = self.intern_ast_path(ast_path);
        let role_key_id = self.intern_string(role_key);
        let authored_summary_id = self.intern_string(authored_summary);
        let materialization_anchor_id = self.intern_string(materialization_anchor);
        self.locators.push(LocatorRow {
            locator_id,
            ast_path_id,
            role_key_id,
            parent_locator_id: None,
            authored_summary_id,
            materialization_anchor_id,
        });
    }

    fn add_record(
        &mut self,
        template_record_id: usize,
        surface_key: &str,
        locator_id: usize,
        resource_name: &str,
        inventory_kind: &str,
        owner_path: &[String],
        semantic_summary: &str,
    ) {
        let surface_key_id = self.intern_string(surface_key);
        let resource_name_id = if resource_name.is_empty() {
            None
        } else {
            Some(self.intern_string(resource_name))
        };
        let inventory_kind_id = self.intern_string(inventory_kind);
        let owner_path_id = self.intern_path(owner_path);
        let semantic_summary_id = self.intern_string(semantic_summary);
        self.records.push(RecordRow {
            template_record_id,
            surface_key_id,
            locator_id,
            resource_name_id,
            inventory_kind_id,
            owner_path_id,
            semantic_summary_id,
        });
    }

    fn add_scope(&mut self, scope: &ScopeSpec) {
        let scope_kind_id = self.intern_string(&scope.scope_kind);
        let ast_path_id = self.intern_ast_path(&scope.ast_path);
        let owner_path_id = self.intern_path(&scope.owner_path);
        let local_binding_set_id = self.intern_binding_set(&scope.local_bindings);
        let argument_set_id = self.intern_binding_set(&scope.arguments);
        self.scopes.push(ScopeRow {
            scope_id: scope.scope_id,
            parent_scope_id: scope.parent_scope_id,
            scope_kind_id,
            ast_path_id,
            owner_path_id,
            local_binding_set_id,
            argument_set_id,
            start_line: scope.start_line,
        });
    }

    fn add_marker(
        &mut self,
        source_order: usize,
        marker_kind: &str,
        source_name: &str,
        ast_path: &str,
        statement_path: Option<&str>,
        scope: &ScopeSpec,
        resource_name: &str,
        flags: Vec<String>,
    ) -> usize {
        let marker_id = self.markers.len();
        let marker_kind_id = self.intern_string(marker_kind);
        let source_name_id = self.intern_string(source_name);
        let operation_key_id = self.intern_string(source_name);
        let owner_path_id = self.intern_path(&scope.owner_path);
        let ast_path_id = self.intern_ast_path(ast_path);
        let statement_path_id = statement_path.map(|path| self.intern_ast_path(path));
        let resource_name_id = if resource_name.is_empty() {
            None
        } else {
            Some(self.intern_string(resource_name))
        };
        self.markers.push(MarkerRow {
            marker_id,
            source_order,
            marker_kind_id,
            source_name_id,
            operation_key_id,
            scope_id: scope.scope_id,
            owner_path_id,
            ast_path_id,
            statement_path_id,
            resource_name_id,
            flags,
        });
        marker_id
    }

    fn add_pyimport_marker(
        &mut self,
        marker_id: usize,
        source_order: usize,
        scope_id: usize,
        module_path: Option<Vec<String>>,
        names: Vec<String>,
        as_name: Option<String>,
        flags: Vec<String>,
    ) {
        let pyimport_marker_id = self.pyimport_markers.len();
        let module_path_id = module_path
            .as_ref()
            .map(|path| self.intern_path(path.as_slice()));
        let name_ids = names
            .iter()
            .map(|name| self.intern_string(name))
            .collect::<Vec<_>>();
        let as_name_id = as_name.as_ref().map(|name| self.intern_string(name));
        self.pyimport_markers.push(PyImportMarkerRow {
            pyimport_marker_id,
            marker_id,
            module_path_id,
            name_ids,
            as_name_id,
            flags: flags.clone(),
        });
        if !names.is_empty() {
            for name in names {
                self.add_managed_import(
                    marker_id,
                    source_order,
                    scope_id,
                    module_path.as_deref(),
                    &name,
                    Some(&name),
                    flags.clone(),
                );
            }
            return;
        }
        if let Some(as_name) = as_name {
            self.add_managed_import(
                marker_id,
                source_order,
                scope_id,
                module_path.as_deref(),
                &as_name,
                None,
                flags,
            );
            return;
        }
        if let Some(module_path) = module_path {
            if module_path.len() == 1 {
                self.add_managed_import(
                    marker_id,
                    source_order,
                    scope_id,
                    Some(module_path.as_slice()),
                    &module_path[0],
                    None,
                    flags,
                );
            }
        }
    }

    fn add_managed_import(
        &mut self,
        marker_id: usize,
        source_order: usize,
        scope_id: usize,
        module_path: Option<&[String]>,
        final_local_name: &str,
        original_symbol: Option<&str>,
        flags: Vec<String>,
    ) {
        let managed_import_id = self.managed_imports.len();
        let module_path_id = module_path.map(|path| self.intern_path(path));
        let final_local_name_id = self.intern_string(final_local_name);
        let original_symbol_id = original_symbol.map(|symbol| self.intern_string(symbol));
        self.managed_imports.push(ManagedImportRow {
            managed_import_id,
            marker_id,
            source_order,
            scope_id,
            module_path_id,
            final_local_name_id,
            original_symbol_id,
            flags,
        });
    }

    fn add_comment_marker(&mut self, marker_id: usize, payload: &str) {
        let comment_marker_id = self.comment_markers.len();
        let payload_id = self.intern_string(payload);
        self.comment_markers.push(CommentMarkerRow {
            comment_marker_id,
            marker_id,
            payload_id,
            flags: vec![
                "strip_for_executable".to_string(),
                "preserve_for_commented_source".to_string(),
            ],
        });
    }

    fn add_ref_marker(
        &mut self,
        marker_id: usize,
        ref_kind: &str,
        context: &str,
        sentinel_attr: &str,
        literal_path: Option<Vec<String>>,
        flags: Vec<String>,
    ) {
        let ref_marker_id = self.ref_markers.len();
        let ref_kind_id = self.intern_string(ref_kind);
        let context_id = self.intern_string(context);
        let sentinel_attr_id = if sentinel_attr.is_empty() {
            None
        } else {
            Some(self.intern_string(sentinel_attr))
        };
        let literal_path_id = literal_path
            .as_ref()
            .map(|path| self.intern_path(path.as_slice()));
        self.ref_markers.push(RefMarkerRow {
            ref_marker_id,
            marker_id,
            ref_kind_id,
            context_id,
            sentinel_attr_id,
            literal_path_id,
            flags,
        });
    }

    fn add_unroll_marker(
        &mut self,
        marker_id: usize,
        statement_path: &str,
        target_ast_path: &str,
        iter_ast_path: &str,
        domain_ast_path: &str,
        body_path: &str,
        orelse_path: Option<&str>,
        target_bindings: Vec<String>,
        domain_shape: &str,
        flags: Vec<String>,
    ) {
        let unroll_marker_id = self.unroll_markers.len();
        let statement_path_id = self.intern_ast_path(statement_path);
        let target_ast_path_id = self.intern_ast_path(target_ast_path);
        let iter_ast_path_id = self.intern_ast_path(iter_ast_path);
        let domain_ast_path_id = self.intern_ast_path(domain_ast_path);
        let body_path_id = self.intern_ast_path(body_path);
        let orelse_path_id = orelse_path.map(|path| self.intern_ast_path(path));
        let target_binding_set_id = self.intern_binding_set(&target_bindings);
        let domain_shape_id = self.intern_string(domain_shape);
        self.unroll_markers.push(UnrollMarkerRow {
            unroll_marker_id,
            marker_id,
            statement_path_id,
            target_ast_path_id,
            iter_ast_path_id,
            domain_ast_path_id,
            body_path_id,
            orelse_path_id,
            target_binding_set_id,
            domain_shape_id,
            flags,
        });
    }

    fn marker_id_for(&self, source_name: &str, ast_path: &str) -> PyResult<usize> {
        self.markers
            .iter()
            .find(|row| {
                self.strings[row.source_name_id] == source_name
                    && self.ast_paths[row.ast_path_id] == ast_path
            })
            .map(|row| row.marker_id)
            .ok_or_else(|| {
                crate::errors::schema_error(&format!(
                    "native package marker row is missing for {source_name} at {ast_path}"
                ))
            })
    }

    pub(crate) fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let snapshot = PyDict::new(py);
        snapshot.set_item("schema", PACKAGE_SCHEMA)?;
        snapshot.set_item("surface_bundle_signature", &self.strings[0])?;
        snapshot.set_item("template_key", &self.strings[1])?;
        snapshot.set_item("source_summary", &self.strings[2])?;
        snapshot.set_item("string_table", &self.strings)?;
        snapshot.set_item("path_table", &self.paths)?;
        snapshot.set_item("ast_path_table", &self.ast_paths)?;
        snapshot.set_item("binding_sets", self.binding_set_list(py)?)?;
        snapshot.set_item("locators", self.locator_list(py)?)?;
        snapshot.set_item("records", self.record_list(py)?)?;
        snapshot.set_item("scopes", self.scope_list(py)?)?;
        snapshot.set_item("markers", self.marker_list(py)?)?;
        snapshot.set_item("pyimport_markers", self.pyimport_marker_list(py)?)?;
        snapshot.set_item("managed_imports", self.managed_import_list(py)?)?;
        snapshot.set_item("comment_markers", self.comment_marker_list(py)?)?;
        snapshot.set_item("ref_markers", self.ref_marker_list(py)?)?;
        snapshot.set_item("unroll_markers", self.unroll_marker_list(py)?)?;
        Ok(snapshot.into_any().unbind())
    }

    fn binding_set_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for (binding_set_id, name_ids) in &self.binding_sets {
            let item = PyDict::new(py);
            item.set_item("binding_set_id", binding_set_id)?;
            item.set_item("names", self.strings_for_ids(name_ids))?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn locator_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.locators {
            let item = PyDict::new(py);
            item.set_item("ast_path", &self.ast_paths[row.ast_path_id])?;
            item.set_item("authored_summary", &self.strings[row.authored_summary_id])?;
            item.set_item("locator_id", row.locator_id)?;
            item.set_item(
                "materialization_anchor",
                &self.strings[row.materialization_anchor_id],
            )?;
            item.set_item("parent_locator_id", row.parent_locator_id)?;
            item.set_item("role_key", &self.strings[row.role_key_id])?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn record_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.records {
            let item = PyDict::new(py);
            item.set_item("flags", Vec::<String>::new())?;
            item.set_item("inventory_kind", &self.strings[row.inventory_kind_id])?;
            item.set_item("locator_id", row.locator_id)?;
            item.set_item("operation_key", "")?;
            item.set_item("owner_path", &self.paths[row.owner_path_id])?;
            item.set_item(
                "resource_name",
                row.resource_name_id
                    .map(|id| self.strings[id].as_str())
                    .unwrap_or(""),
            )?;
            item.set_item("semantic_summary", &self.strings[row.semantic_summary_id])?;
            item.set_item("surface_key", &self.strings[row.surface_key_id])?;
            item.set_item("template_record_id", row.template_record_id)?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn scope_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.scopes {
            let item = PyDict::new(py);
            item.set_item("arguments", self.binding_set_names(row.argument_set_id))?;
            item.set_item("ast_path", &self.ast_paths[row.ast_path_id])?;
            item.set_item(
                "local_bindings",
                self.binding_set_names(row.local_binding_set_id),
            )?;
            item.set_item("owner_path", &self.paths[row.owner_path_id])?;
            item.set_item("parent_scope_id", row.parent_scope_id)?;
            item.set_item("scope_id", row.scope_id)?;
            item.set_item("scope_kind", &self.strings[row.scope_kind_id])?;
            item.set_item("start_line", row.start_line)?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn marker_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.markers {
            let item = PyDict::new(py);
            item.set_item("ast_path", &self.ast_paths[row.ast_path_id])?;
            item.set_item("flags", &row.flags)?;
            item.set_item("marker_id", row.marker_id)?;
            item.set_item("marker_kind", &self.strings[row.marker_kind_id])?;
            item.set_item("operation_key", &self.strings[row.operation_key_id])?;
            item.set_item("owner_path", &self.paths[row.owner_path_id])?;
            item.set_item(
                "resource_name",
                row.resource_name_id
                    .map(|id| self.strings[id].as_str())
                    .unwrap_or(""),
            )?;
            item.set_item("scope_id", row.scope_id)?;
            item.set_item("source_name", &self.strings[row.source_name_id])?;
            item.set_item("source_order", row.source_order)?;
            match row.statement_path_id {
                Some(path_id) => item.set_item("statement_path", &self.ast_paths[path_id])?,
                None => item.set_item("statement_path", py.None())?,
            };
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn pyimport_marker_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.pyimport_markers {
            let item = PyDict::new(py);
            item.set_item(
                "as_name",
                row.as_name_id
                    .map(|id| self.strings[id].as_str())
                    .unwrap_or(""),
            )?;
            item.set_item("flags", &row.flags)?;
            item.set_item("marker_id", row.marker_id)?;
            match row.module_path_id {
                Some(path_id) => item.set_item("module_path", &self.paths[path_id])?,
                None => item.set_item("module_path", py.None())?,
            };
            item.set_item("names", self.strings_for_ids(&row.name_ids))?;
            item.set_item("pyimport_marker_id", row.pyimport_marker_id)?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn managed_import_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.managed_imports {
            let item = PyDict::new(py);
            item.set_item("final_local_name", &self.strings[row.final_local_name_id])?;
            item.set_item("flags", &row.flags)?;
            item.set_item("managed_import_id", row.managed_import_id)?;
            item.set_item("marker_id", row.marker_id)?;
            match row.module_path_id {
                Some(path_id) => item.set_item("module_path", &self.paths[path_id])?,
                None => item.set_item("module_path", py.None())?,
            };
            match row.original_symbol_id {
                Some(string_id) => item.set_item("original_symbol", &self.strings[string_id])?,
                None => item.set_item("original_symbol", py.None())?,
            };
            item.set_item("scope_id", row.scope_id)?;
            item.set_item("source_order", row.source_order)?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn comment_marker_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.comment_markers {
            let item = PyDict::new(py);
            item.set_item("comment_marker_id", row.comment_marker_id)?;
            item.set_item("flags", &row.flags)?;
            item.set_item("marker_id", row.marker_id)?;
            item.set_item("payload", &self.strings[row.payload_id])?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn ref_marker_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.ref_markers {
            let item = PyDict::new(py);
            item.set_item("context", &self.strings[row.context_id])?;
            item.set_item("flags", &row.flags)?;
            match row.literal_path_id {
                Some(path_id) => item.set_item("literal_path", &self.paths[path_id])?,
                None => item.set_item("literal_path", py.None())?,
            };
            item.set_item("marker_id", row.marker_id)?;
            item.set_item("ref_kind", &self.strings[row.ref_kind_id])?;
            item.set_item("ref_marker_id", row.ref_marker_id)?;
            item.set_item(
                "sentinel_attr",
                row.sentinel_attr_id
                    .map(|id| self.strings[id].as_str())
                    .unwrap_or(""),
            )?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn unroll_marker_list(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for row in &self.unroll_markers {
            let item = PyDict::new(py);
            item.set_item("body_path", &self.ast_paths[row.body_path_id])?;
            item.set_item("domain_ast_path", &self.ast_paths[row.domain_ast_path_id])?;
            item.set_item("domain_shape", &self.strings[row.domain_shape_id])?;
            item.set_item("flags", &row.flags)?;
            item.set_item("iter_ast_path", &self.ast_paths[row.iter_ast_path_id])?;
            item.set_item("marker_id", row.marker_id)?;
            match row.orelse_path_id {
                Some(path_id) => item.set_item("orelse_path", &self.ast_paths[path_id])?,
                None => item.set_item("orelse_path", py.None())?,
            };
            item.set_item("statement_path", &self.ast_paths[row.statement_path_id])?;
            item.set_item("target_ast_path", &self.ast_paths[row.target_ast_path_id])?;
            item.set_item(
                "target_bindings",
                self.binding_set_names(row.target_binding_set_id),
            )?;
            item.set_item("unroll_marker_id", row.unroll_marker_id)?;
            list.append(item)?;
        }
        Ok(list.into_any().unbind())
    }

    fn strings_for_ids(&self, ids: &[usize]) -> Vec<&str> {
        ids.iter().map(|id| self.strings[*id].as_str()).collect()
    }

    fn binding_set_names(&self, binding_set_id: usize) -> Vec<&str> {
        self.strings_for_ids(&self.binding_sets[binding_set_id].1)
    }

    pub(crate) fn package_marker_hygiene_specs(&self) -> Vec<PackageMarkerHygieneSpec> {
        self.markers
            .iter()
            .filter_map(|marker| {
                let source_name = self.strings[marker.source_name_id].as_str();
                if !matches!(
                    source_name,
                    "astichi_export" | "astichi_import" | "astichi_keep" | "astichi_pass"
                ) {
                    return None;
                }
                Some(PackageMarkerHygieneSpec {
                    source_name: source_name.to_string(),
                    resource_name: marker
                        .resource_name_id
                        .map(|id| self.strings[id].clone())
                        .unwrap_or_default(),
                    scope_id: marker.scope_id,
                })
            })
            .collect()
    }

    pub(crate) fn managed_import_hygiene_specs(&self) -> Vec<ManagedImportHygieneSpec> {
        self.managed_imports
            .iter()
            .filter_map(|row| {
                let module_path_id = row.module_path_id?;
                Some(ManagedImportHygieneSpec {
                    final_local_name: self.strings[row.final_local_name_id].clone(),
                    module_path: self.paths[module_path_id].clone(),
                    original_symbol: row.original_symbol_id.map(|id| self.strings[id].clone()),
                })
            })
            .collect()
    }

    pub(crate) fn pyimport_existing_binding_names(&self) -> BTreeSet<String> {
        self.scopes
            .first()
            .map(|scope| self.binding_name_set(scope.local_binding_set_id))
            .unwrap_or_default()
    }

    pub(crate) fn binding_names_for_scope_id(&self, scope_id: usize) -> BTreeSet<String> {
        self.scopes
            .iter()
            .find(|scope| scope.scope_id == scope_id)
            .map(|scope| self.binding_name_set(scope.local_binding_set_id))
            .unwrap_or_default()
    }

    pub(crate) fn root_scope_id(&self) -> Option<usize> {
        self.scopes.first().map(|scope| scope.scope_id)
    }

    pub(crate) fn boundary_available_names_for_statement_path(
        &self,
        statement_path: &str,
    ) -> BTreeSet<String> {
        self.scope_id_for_statement_path(statement_path)
            .map(|scope_id| self.binding_names_for_scope_id(scope_id))
            .unwrap_or_default()
    }

    pub(crate) fn scope_id_for_statement_path(&self, statement_path: &str) -> Option<usize> {
        let mut best_scope_id = None;
        let mut best_depth = 0;
        for scope in &self.scopes {
            let scope_path = &self.ast_paths[scope.ast_path_id];
            if !ast_path_is_prefix(scope_path, statement_path) {
                continue;
            }
            let depth = ast_path_depth(scope_path);
            if best_scope_id.is_none() || depth > best_depth {
                best_scope_id = Some(scope.scope_id);
                best_depth = depth;
            }
        }
        best_scope_id
    }

    pub(crate) fn locator_ast_path_for_record(&self, template_record_index: usize) -> Option<&str> {
        let record = self
            .records
            .iter()
            .find(|record| record.template_record_id == template_record_index)?;
        let locator = self
            .locators
            .iter()
            .find(|locator| locator.locator_id == record.locator_id)?;
        Some(self.ast_paths[locator.ast_path_id].as_str())
    }

    pub(crate) fn unresolved_capable_record_indexes(&self) -> Vec<usize> {
        self.records
            .iter()
            .filter_map(|record| {
                let inventory_kind = &self.strings[record.inventory_kind_id];
                if is_unresolved_capable_inventory_kind(inventory_kind) {
                    Some(record.template_record_id)
                } else {
                    None
                }
            })
            .collect()
    }

    fn binding_name_set(&self, binding_set_id: usize) -> BTreeSet<String> {
        self.binding_sets[binding_set_id]
            .1
            .iter()
            .map(|id| self.strings[*id].clone())
            .collect()
    }
}

fn is_unresolved_capable_inventory_kind(inventory_kind: &str) -> bool {
    inventory_kind.starts_with("hole.")
        || inventory_kind.ends_with(".demand")
        || inventory_kind == "external.bind"
}

fn extract_scopes(
    module: &ast::ModModule,
    source_map: &crate::template_extract::SourceMap,
    module_start_line: u32,
) -> Vec<ScopeSpec> {
    let mut scopes = Vec::new();
    let module_scope = ScopeSpec {
        scope_id: 0,
        parent_scope_id: None,
        scope_kind: "module".to_string(),
        ast_path: "".to_string(),
        owner_path: Vec::new(),
        local_bindings: scope_body_bindings(&module.body, Vec::new()),
        arguments: Vec::new(),
        start_line: Some(module_start_line),
    };
    scopes.push(module_scope);
    for (index, stmt) in module.body.iter().enumerate() {
        visit_stmt_scopes(
            stmt,
            &format!("body[{index}]"),
            0,
            &[],
            source_map,
            &mut scopes,
        );
    }
    scopes
}

fn visit_stmt_scopes(
    stmt: &ast::Stmt,
    path: &str,
    parent_scope_id: usize,
    owner_path: &[String],
    source_map: &crate::template_extract::SourceMap,
    scopes: &mut Vec<ScopeSpec>,
) {
    match stmt {
        ast::Stmt::FunctionDef(node) => {
            let mut child_owner = owner_path.to_vec();
            child_owner.push(node.name.to_string());
            let arguments = argument_names(&node.args);
            let scope_id = scopes.len();
            scopes.push(ScopeSpec {
                scope_id,
                parent_scope_id: Some(parent_scope_id),
                scope_kind: "function".to_string(),
                ast_path: path.to_string(),
                owner_path: child_owner.clone(),
                local_bindings: scope_body_bindings(&node.body, arguments.clone()),
                arguments,
                start_line: Some(source_map.line(node.range) as u32),
            });
            visit_body_scopes(
                &node.body,
                &format!("{path}/body"),
                scope_id,
                &child_owner,
                source_map,
                scopes,
            );
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            let mut child_owner = owner_path.to_vec();
            child_owner.push(node.name.to_string());
            let arguments = argument_names(&node.args);
            let scope_id = scopes.len();
            scopes.push(ScopeSpec {
                scope_id,
                parent_scope_id: Some(parent_scope_id),
                scope_kind: "async_function".to_string(),
                ast_path: path.to_string(),
                owner_path: child_owner.clone(),
                local_bindings: scope_body_bindings(&node.body, arguments.clone()),
                arguments,
                start_line: Some(source_map.line(node.range) as u32),
            });
            visit_body_scopes(
                &node.body,
                &format!("{path}/body"),
                scope_id,
                &child_owner,
                source_map,
                scopes,
            );
        }
        ast::Stmt::ClassDef(node) => {
            let mut child_owner = owner_path.to_vec();
            child_owner.push(node.name.to_string());
            let scope_id = scopes.len();
            scopes.push(ScopeSpec {
                scope_id,
                parent_scope_id: Some(parent_scope_id),
                scope_kind: "class".to_string(),
                ast_path: path.to_string(),
                owner_path: child_owner.clone(),
                local_bindings: scope_body_bindings(&node.body, Vec::new()),
                arguments: Vec::new(),
                start_line: Some(source_map.line(node.range) as u32),
            });
            visit_body_scopes(
                &node.body,
                &format!("{path}/body"),
                scope_id,
                &child_owner,
                source_map,
                scopes,
            );
        }
        ast::Stmt::For(node) => {
            visit_body_scopes(
                &node.body,
                &format!("{path}/body"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
            visit_body_scopes(
                &node.orelse,
                &format!("{path}/orelse"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
        }
        ast::Stmt::While(node) => {
            visit_body_scopes(
                &node.body,
                &format!("{path}/body"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
            visit_body_scopes(
                &node.orelse,
                &format!("{path}/orelse"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
        }
        ast::Stmt::If(node) => {
            visit_body_scopes(
                &node.body,
                &format!("{path}/body"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
            visit_body_scopes(
                &node.orelse,
                &format!("{path}/orelse"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
        }
        ast::Stmt::With(node) => {
            visit_body_scopes(
                &node.body,
                &format!("{path}/body"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
        }
        ast::Stmt::Try(node) => {
            visit_body_scopes(
                &node.body,
                &format!("{path}/body"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
            for (index, handler) in node.handlers.iter().enumerate() {
                let ast::ExceptHandler::ExceptHandler(handler) = handler;
                visit_body_scopes(
                    &handler.body,
                    &format!("{path}/handlers[{index}]/body"),
                    parent_scope_id,
                    owner_path,
                    source_map,
                    scopes,
                );
            }
            visit_body_scopes(
                &node.orelse,
                &format!("{path}/orelse"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
            visit_body_scopes(
                &node.finalbody,
                &format!("{path}/finalbody"),
                parent_scope_id,
                owner_path,
                source_map,
                scopes,
            );
        }
        _ => {}
    }
}

fn visit_body_scopes(
    body: &[ast::Stmt],
    parent_path: &str,
    parent_scope_id: usize,
    owner_path: &[String],
    source_map: &crate::template_extract::SourceMap,
    scopes: &mut Vec<ScopeSpec>,
) {
    for (index, stmt) in body.iter().enumerate() {
        visit_stmt_scopes(
            stmt,
            &format!("{parent_path}[{index}]"),
            parent_scope_id,
            owner_path,
            source_map,
            scopes,
        );
    }
}

fn scope_body_bindings(body: &[ast::Stmt], initial: Vec<String>) -> Vec<String> {
    let mut names = initial.into_iter().collect::<BTreeSet<_>>();
    for stmt in body {
        collect_stmt_bindings(stmt, &mut names);
    }
    names.into_iter().collect()
}

fn collect_stmt_bindings(stmt: &ast::Stmt, names: &mut BTreeSet<String>) {
    match stmt {
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
                collect_target_bindings(target, names);
            }
            collect_expr_bindings(&node.value, names);
        }
        ast::Stmt::AnnAssign(node) => {
            collect_target_bindings(&node.target, names);
            collect_expr_bindings(&node.annotation, names);
            if let Some(value) = node.value.as_ref() {
                collect_expr_bindings(value, names);
            }
        }
        ast::Stmt::AugAssign(node) => {
            collect_target_bindings(&node.target, names);
            collect_expr_bindings(&node.value, names);
        }
        ast::Stmt::Delete(node) => {
            for target in &node.targets {
                collect_target_bindings(target, names);
            }
        }
        ast::Stmt::Expr(node) => collect_expr_bindings(&node.value, names),
        ast::Stmt::Return(node) => {
            if let Some(value) = node.value.as_ref() {
                collect_expr_bindings(value, names);
            }
        }
        ast::Stmt::For(node) => {
            collect_target_bindings(&node.target, names);
            collect_expr_bindings(&node.iter, names);
            for stmt in &node.body {
                collect_stmt_bindings(stmt, names);
            }
            for stmt in &node.orelse {
                collect_stmt_bindings(stmt, names);
            }
        }
        ast::Stmt::While(node) => {
            collect_expr_bindings(&node.test, names);
            for stmt in &node.body {
                collect_stmt_bindings(stmt, names);
            }
            for stmt in &node.orelse {
                collect_stmt_bindings(stmt, names);
            }
        }
        ast::Stmt::If(node) => {
            collect_expr_bindings(&node.test, names);
            for stmt in &node.body {
                collect_stmt_bindings(stmt, names);
            }
            for stmt in &node.orelse {
                collect_stmt_bindings(stmt, names);
            }
        }
        ast::Stmt::With(node) => {
            for item in &node.items {
                collect_expr_bindings(&item.context_expr, names);
                if let Some(optional_vars) = item.optional_vars.as_ref() {
                    collect_target_bindings(optional_vars, names);
                }
            }
            for stmt in &node.body {
                collect_stmt_bindings(stmt, names);
            }
        }
        ast::Stmt::Try(node) => {
            for stmt in &node.body {
                collect_stmt_bindings(stmt, names);
            }
            for handler in &node.handlers {
                let ast::ExceptHandler::ExceptHandler(handler) = handler;
                if let Some(type_) = handler.type_.as_ref() {
                    collect_expr_bindings(type_, names);
                }
                for stmt in &handler.body {
                    collect_stmt_bindings(stmt, names);
                }
            }
            for stmt in &node.orelse {
                collect_stmt_bindings(stmt, names);
            }
            for stmt in &node.finalbody {
                collect_stmt_bindings(stmt, names);
            }
        }
        ast::Stmt::Import(node) => {
            for alias in &node.names {
                names.insert(import_alias_binding_name(alias, false));
            }
        }
        ast::Stmt::ImportFrom(node) => {
            for alias in &node.names {
                names.insert(import_alias_binding_name(alias, true));
            }
        }
        _ => {}
    }
}

fn collect_target_bindings(expr: &ast::Expr, names: &mut BTreeSet<String>) {
    match expr {
        ast::Expr::Name(node) => {
            names.insert(node.id.to_string());
        }
        ast::Expr::Tuple(node) => {
            for item in &node.elts {
                collect_target_bindings(item, names);
            }
        }
        ast::Expr::List(node) => {
            for item in &node.elts {
                collect_target_bindings(item, names);
            }
        }
        ast::Expr::Starred(node) => collect_target_bindings(&node.value, names),
        _ => {}
    }
}

fn collect_expr_bindings(expr: &ast::Expr, names: &mut BTreeSet<String>) {
    match expr {
        ast::Expr::NamedExpr(node) => {
            collect_target_bindings(&node.target, names);
            collect_expr_bindings(&node.value, names);
        }
        ast::Expr::BoolOp(node) => {
            for value in &node.values {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::BinOp(node) => {
            collect_expr_bindings(&node.left, names);
            collect_expr_bindings(&node.right, names);
        }
        ast::Expr::UnaryOp(node) => collect_expr_bindings(&node.operand, names),
        ast::Expr::Lambda(node) => collect_expr_bindings(&node.body, names),
        ast::Expr::IfExp(node) => {
            collect_expr_bindings(&node.test, names);
            collect_expr_bindings(&node.body, names);
            collect_expr_bindings(&node.orelse, names);
        }
        ast::Expr::Dict(node) => {
            for key in node.keys.iter().flatten() {
                collect_expr_bindings(key, names);
            }
            for value in &node.values {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::Set(node) => {
            for value in &node.elts {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::List(node) => {
            for value in &node.elts {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::Tuple(node) => {
            for value in &node.elts {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::Call(node) => {
            collect_expr_bindings(&node.func, names);
            for arg in &node.args {
                collect_expr_bindings(arg, names);
            }
            for keyword in &node.keywords {
                collect_expr_bindings(&keyword.value, names);
            }
        }
        ast::Expr::Attribute(node) => collect_expr_bindings(&node.value, names),
        ast::Expr::Subscript(node) => {
            collect_expr_bindings(&node.value, names);
            collect_expr_bindings(&node.slice, names);
        }
        ast::Expr::Starred(node) => collect_expr_bindings(&node.value, names),
        ast::Expr::Compare(node) => {
            collect_expr_bindings(&node.left, names);
            for comparator in &node.comparators {
                collect_expr_bindings(comparator, names);
            }
        }
        ast::Expr::FormattedValue(node) => {
            collect_expr_bindings(&node.value, names);
            if let Some(value) = node.format_spec.as_ref() {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::JoinedStr(node) => {
            for value in &node.values {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::ListComp(node) => {
            collect_expr_bindings(&node.elt, names);
            collect_comprehension_bindings(&node.generators, names);
        }
        ast::Expr::SetComp(node) => {
            collect_expr_bindings(&node.elt, names);
            collect_comprehension_bindings(&node.generators, names);
        }
        ast::Expr::DictComp(node) => {
            collect_expr_bindings(&node.key, names);
            collect_expr_bindings(&node.value, names);
            collect_comprehension_bindings(&node.generators, names);
        }
        ast::Expr::GeneratorExp(node) => {
            collect_expr_bindings(&node.elt, names);
            collect_comprehension_bindings(&node.generators, names);
        }
        ast::Expr::Await(node) => collect_expr_bindings(&node.value, names),
        ast::Expr::Yield(node) => {
            if let Some(value) = node.value.as_ref() {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::YieldFrom(node) => collect_expr_bindings(&node.value, names),
        ast::Expr::Slice(node) => {
            if let Some(value) = node.lower.as_ref() {
                collect_expr_bindings(value, names);
            }
            if let Some(value) = node.upper.as_ref() {
                collect_expr_bindings(value, names);
            }
            if let Some(value) = node.step.as_ref() {
                collect_expr_bindings(value, names);
            }
        }
        ast::Expr::Constant(_) | ast::Expr::Name(_) => {}
    }
}

fn collect_comprehension_bindings(
    comprehensions: &[ast::Comprehension],
    names: &mut BTreeSet<String>,
) {
    for comprehension in comprehensions {
        collect_target_bindings(&comprehension.target, names);
        collect_expr_bindings(&comprehension.iter, names);
        for condition in &comprehension.ifs {
            collect_expr_bindings(condition, names);
        }
    }
}

fn argument_names(args: &ast::Arguments) -> Vec<String> {
    let mut names = BTreeSet::new();
    for arg in &args.posonlyargs {
        names.insert(arg.def.arg.to_string());
    }
    for arg in &args.args {
        names.insert(arg.def.arg.to_string());
    }
    for arg in &args.kwonlyargs {
        names.insert(arg.def.arg.to_string());
    }
    if let Some(arg) = args.vararg.as_ref() {
        names.insert(arg.arg.to_string());
    }
    if let Some(arg) = args.kwarg.as_ref() {
        names.insert(arg.arg.to_string());
    }
    names.into_iter().collect()
}

fn import_alias_binding_name(alias: &ast::Alias, from_import: bool) -> String {
    if let Some(asname) = alias.asname.as_ref() {
        return asname.to_string();
    }
    if from_import {
        return alias.name.to_string();
    }
    alias
        .name
        .as_str()
        .split('.')
        .next()
        .unwrap_or(alias.name.as_str())
        .to_string()
}

fn extract_typed_marker_rows_stmt(
    stmt: &ast::Stmt,
    path: &str,
    package: &mut PackageBuilder,
) -> PyResult<()> {
    match stmt {
        ast::Stmt::Expr(node) => {
            if is_ref_statement_expr(&node.value) {
                return Err(crate::errors::schema_error(
                    "unsupported astichi_ref statement context",
                ));
            }
            extract_ref_rows_expr(&node.value, &format!("{path}/value"), Some(path), package)
        }
        ast::Stmt::Assign(node) => {
            for (index, target) in node.targets.iter().enumerate() {
                extract_ref_rows_expr(
                    target,
                    &format!("{path}/targets[{index}]"),
                    Some(path),
                    package,
                )?;
            }
            extract_ref_rows_expr(&node.value, &format!("{path}/value"), Some(path), package)
        }
        ast::Stmt::AnnAssign(node) => {
            extract_ref_rows_expr(&node.target, &format!("{path}/target"), Some(path), package)?;
            extract_ref_rows_expr(
                &node.annotation,
                &format!("{path}/annotation"),
                Some(path),
                package,
            )?;
            if let Some(value) = node.value.as_ref() {
                extract_ref_rows_expr(value, &format!("{path}/value"), Some(path), package)?;
            }
            Ok(())
        }
        ast::Stmt::AugAssign(node) => {
            extract_ref_rows_expr(&node.target, &format!("{path}/target"), Some(path), package)?;
            extract_ref_rows_expr(&node.value, &format!("{path}/value"), Some(path), package)
        }
        ast::Stmt::Delete(node) => {
            for (index, target) in node.targets.iter().enumerate() {
                extract_ref_rows_expr(
                    target,
                    &format!("{path}/targets[{index}]"),
                    Some(path),
                    package,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Return(node) => {
            if let Some(value) = node.value.as_ref() {
                extract_ref_rows_expr(value, &format!("{path}/value"), Some(path), package)?;
            }
            Ok(())
        }
        ast::Stmt::Assert(node) => {
            extract_ref_rows_expr(&node.test, &format!("{path}/test"), Some(path), package)?;
            if let Some(msg) = node.msg.as_ref() {
                extract_ref_rows_expr(msg, &format!("{path}/msg"), Some(path), package)?;
            }
            Ok(())
        }
        ast::Stmt::Raise(node) => {
            if let Some(exc) = node.exc.as_ref() {
                extract_ref_rows_expr(exc, &format!("{path}/exc"), Some(path), package)?;
            }
            if let Some(cause) = node.cause.as_ref() {
                extract_ref_rows_expr(cause, &format!("{path}/cause"), Some(path), package)?;
            }
            Ok(())
        }
        ast::Stmt::For(node) => {
            let iter_path = format!("{path}/iter");
            if call_expr_name(&node.iter) == Some("astichi_for") {
                add_unroll_row(node, path, &iter_path, package)?;
            }
            extract_ref_rows_expr(&node.target, &format!("{path}/target"), Some(path), package)?;
            extract_ref_rows_expr(&node.iter, &iter_path, Some(path), package)?;
            extract_typed_marker_rows_stmt_list(&node.body, &format!("{path}/body"), package)?;
            extract_typed_marker_rows_stmt_list(&node.orelse, &format!("{path}/orelse"), package)
        }
        ast::Stmt::While(node) => {
            extract_ref_rows_expr(&node.test, &format!("{path}/test"), Some(path), package)?;
            extract_typed_marker_rows_stmt_list(&node.body, &format!("{path}/body"), package)?;
            extract_typed_marker_rows_stmt_list(&node.orelse, &format!("{path}/orelse"), package)
        }
        ast::Stmt::If(node) => {
            extract_ref_rows_expr(&node.test, &format!("{path}/test"), Some(path), package)?;
            extract_typed_marker_rows_stmt_list(&node.body, &format!("{path}/body"), package)?;
            extract_typed_marker_rows_stmt_list(&node.orelse, &format!("{path}/orelse"), package)
        }
        ast::Stmt::With(node) => {
            for (index, item) in node.items.iter().enumerate() {
                extract_ref_rows_expr(
                    &item.context_expr,
                    &format!("{path}/items[{index}]/context_expr"),
                    Some(path),
                    package,
                )?;
                if let Some(optional_vars) = item.optional_vars.as_ref() {
                    extract_ref_rows_expr(
                        optional_vars,
                        &format!("{path}/items[{index}]/optional_vars"),
                        Some(path),
                        package,
                    )?;
                }
            }
            extract_typed_marker_rows_stmt_list(&node.body, &format!("{path}/body"), package)
        }
        ast::Stmt::FunctionDef(node) => {
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                extract_ref_rows_expr(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    package,
                )?;
            }
            extract_ref_rows_arguments(
                &node.args,
                &format!("{path}/args"),
                Some(path),
                package,
            )?;
            extract_typed_marker_rows_stmt_list(&node.body, &format!("{path}/body"), package)?;
            if let Some(returns) = node.returns.as_ref() {
                extract_ref_rows_expr(returns, &format!("{path}/returns"), Some(path), package)?;
            }
            Ok(())
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                extract_ref_rows_expr(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    package,
                )?;
            }
            extract_ref_rows_arguments(
                &node.args,
                &format!("{path}/args"),
                Some(path),
                package,
            )?;
            extract_typed_marker_rows_stmt_list(&node.body, &format!("{path}/body"), package)?;
            if let Some(returns) = node.returns.as_ref() {
                extract_ref_rows_expr(returns, &format!("{path}/returns"), Some(path), package)?;
            }
            Ok(())
        }
        ast::Stmt::ClassDef(node) => {
            for (index, base) in node.bases.iter().enumerate() {
                extract_ref_rows_expr(
                    base,
                    &format!("{path}/bases[{index}]"),
                    Some(path),
                    package,
                )?;
            }
            for (index, keyword) in node.keywords.iter().enumerate() {
                extract_ref_rows_expr(
                    &keyword.value,
                    &format!("{path}/keywords[{index}]/value"),
                    Some(path),
                    package,
                )?;
            }
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                extract_ref_rows_expr(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    package,
                )?;
            }
            extract_typed_marker_rows_stmt_list(&node.body, &format!("{path}/body"), package)
        }
        ast::Stmt::Try(node) => {
            extract_typed_marker_rows_stmt_list(&node.body, &format!("{path}/body"), package)?;
            for (index, handler) in node.handlers.iter().enumerate() {
                let ast::ExceptHandler::ExceptHandler(handler) = handler;
                if let Some(type_) = handler.type_.as_ref() {
                    extract_ref_rows_expr(
                        type_,
                        &format!("{path}/handlers[{index}]/type"),
                        Some(path),
                        package,
                    )?;
                }
                extract_typed_marker_rows_stmt_list(
                    &handler.body,
                    &format!("{path}/handlers[{index}]/body"),
                    package,
                )?;
            }
            extract_typed_marker_rows_stmt_list(&node.orelse, &format!("{path}/orelse"), package)?;
            extract_typed_marker_rows_stmt_list(
                &node.finalbody,
                &format!("{path}/finalbody"),
                package,
            )
        }
        _ => Ok(()),
    }
}

fn extract_typed_marker_rows_stmt_list(
    body: &[ast::Stmt],
    parent_path: &str,
    package: &mut PackageBuilder,
) -> PyResult<()> {
    for (index, stmt) in body.iter().enumerate() {
        extract_typed_marker_rows_stmt(stmt, &format!("{parent_path}[{index}]"), package)?;
    }
    Ok(())
}

fn extract_ref_rows_arguments(
    args: &ast::Arguments,
    path: &str,
    statement_path: Option<&str>,
    package: &mut PackageBuilder,
) -> PyResult<()> {
    let mut default_index = 0usize;
    for (index, arg) in args.posonlyargs.iter().enumerate() {
        extract_ref_rows_arg(
            &arg.def,
            &format!("{path}/posonlyargs[{index}]"),
            statement_path,
            package,
        )?;
        if let Some(default) = arg.default.as_ref() {
            extract_ref_rows_expr(
                default,
                &format!("{path}/defaults[{default_index}]"),
                statement_path,
                package,
            )?;
            default_index += 1;
        }
    }
    for (index, arg) in args.args.iter().enumerate() {
        extract_ref_rows_arg(
            &arg.def,
            &format!("{path}/args[{index}]"),
            statement_path,
            package,
        )?;
        if let Some(default) = arg.default.as_ref() {
            extract_ref_rows_expr(
                default,
                &format!("{path}/defaults[{default_index}]"),
                statement_path,
                package,
            )?;
            default_index += 1;
        }
    }
    if let Some(arg) = args.vararg.as_ref() {
        extract_ref_rows_arg(arg, &format!("{path}/vararg"), statement_path, package)?;
    }
    for (index, arg) in args.kwonlyargs.iter().enumerate() {
        extract_ref_rows_arg(
            &arg.def,
            &format!("{path}/kwonlyargs[{index}]"),
            statement_path,
            package,
        )?;
        if let Some(default) = arg.default.as_ref() {
            extract_ref_rows_expr(
                default,
                &format!("{path}/kw_defaults[{index}]"),
                statement_path,
                package,
            )?;
        }
    }
    if let Some(arg) = args.kwarg.as_ref() {
        extract_ref_rows_arg(arg, &format!("{path}/kwarg"), statement_path, package)?;
    }
    Ok(())
}

fn extract_ref_rows_arg(
    arg: &ast::Arg,
    path: &str,
    statement_path: Option<&str>,
    package: &mut PackageBuilder,
) -> PyResult<()> {
    if let Some(annotation) = arg.annotation.as_ref() {
        extract_ref_rows_expr(
            annotation,
            &format!("{path}/annotation"),
            statement_path,
            package,
        )?;
    }
    Ok(())
}

fn extract_ref_rows_expr(
    expr: &ast::Expr,
    path: &str,
    statement_path: Option<&str>,
    package: &mut PackageBuilder,
) -> PyResult<()> {
    match expr {
        ast::Expr::Call(node) => {
            if call_name(&node.func) == Some("astichi_ref") {
                let marker_id = package.marker_id_for("astichi_ref", path)?;
                package.add_ref_marker(
                    marker_id,
                    "value",
                    "load",
                    "",
                    literal_ref_path(node),
                    vec!["value_form".to_string()],
                );
            }
            extract_ref_rows_expr(&node.func, &format!("{path}/func"), statement_path, package)?;
            for (index, arg) in node.args.iter().enumerate() {
                extract_ref_rows_expr(
                    arg,
                    &format!("{path}/args[{index}]"),
                    statement_path,
                    package,
                )?;
            }
            for (index, keyword) in node.keywords.iter().enumerate() {
                extract_ref_rows_expr(
                    &keyword.value,
                    &format!("{path}/keywords[{index}]/value"),
                    statement_path,
                    package,
                )?;
            }
            Ok(())
        }
        ast::Expr::Attribute(node) => {
            let value_path = format!("{path}/value");
            if is_ref_sentinel_attr(node) {
                let ast::Expr::Call(call) = node.value.as_ref() else {
                    unreachable!("is_ref_sentinel_attr only matches call values");
                };
                let marker_id = package.marker_id_for("astichi_ref", &value_path)?;
                package.add_ref_marker(
                    marker_id,
                    "sentinel_attribute",
                    expr_context_name(node.ctx),
                    node.attr.as_str(),
                    literal_ref_path(call),
                    vec!["sentinel_attribute".to_string()],
                );
                return Ok(());
            }
            extract_ref_rows_expr(&node.value, &value_path, statement_path, package)
        }
        ast::Expr::BoolOp(node) => {
            for (index, value) in node.values.iter().enumerate() {
                extract_ref_rows_expr(
                    value,
                    &format!("{path}/values[{index}]"),
                    statement_path,
                    package,
                )?;
            }
            Ok(())
        }
        ast::Expr::NamedExpr(node) => {
            extract_ref_rows_expr(
                &node.target,
                &format!("{path}/target"),
                statement_path,
                package,
            )?;
            extract_ref_rows_expr(
                &node.value,
                &format!("{path}/value"),
                statement_path,
                package,
            )
        }
        ast::Expr::BinOp(node) => {
            extract_ref_rows_expr(&node.left, &format!("{path}/left"), statement_path, package)?;
            extract_ref_rows_expr(
                &node.right,
                &format!("{path}/right"),
                statement_path,
                package,
            )
        }
        ast::Expr::UnaryOp(node) => extract_ref_rows_expr(
            &node.operand,
            &format!("{path}/operand"),
            statement_path,
            package,
        ),
        ast::Expr::Lambda(node) => {
            extract_ref_rows_arguments(
                &node.args,
                &format!("{path}/args"),
                statement_path,
                package,
            )?;
            extract_ref_rows_expr(&node.body, &format!("{path}/body"), statement_path, package)
        }
        ast::Expr::IfExp(node) => {
            extract_ref_rows_expr(&node.test, &format!("{path}/test"), statement_path, package)?;
            extract_ref_rows_expr(&node.body, &format!("{path}/body"), statement_path, package)?;
            extract_ref_rows_expr(
                &node.orelse,
                &format!("{path}/orelse"),
                statement_path,
                package,
            )
        }
        ast::Expr::Dict(node) => {
            for (index, key) in node.keys.iter().enumerate() {
                if let Some(key) = key {
                    extract_ref_rows_expr(
                        key,
                        &format!("{path}/keys[{index}]"),
                        statement_path,
                        package,
                    )?;
                }
            }
            for (index, value) in node.values.iter().enumerate() {
                extract_ref_rows_expr(
                    value,
                    &format!("{path}/values[{index}]"),
                    statement_path,
                    package,
                )?;
            }
            Ok(())
        }
        ast::Expr::Set(node) => {
            extract_ref_rows_expr_list(&node.elts, path, "elts", statement_path, package)
        }
        ast::Expr::List(node) => {
            extract_ref_rows_expr_list(&node.elts, path, "elts", statement_path, package)
        }
        ast::Expr::Tuple(node) => {
            extract_ref_rows_expr_list(&node.elts, path, "elts", statement_path, package)
        }
        ast::Expr::Subscript(node) => {
            extract_ref_rows_expr(
                &node.value,
                &format!("{path}/value"),
                statement_path,
                package,
            )?;
            extract_ref_rows_expr(
                &node.slice,
                &format!("{path}/slice"),
                statement_path,
                package,
            )
        }
        ast::Expr::Starred(node) => extract_ref_rows_expr(
            &node.value,
            &format!("{path}/value"),
            statement_path,
            package,
        ),
        ast::Expr::Compare(node) => {
            extract_ref_rows_expr(&node.left, &format!("{path}/left"), statement_path, package)?;
            for (index, value) in node.comparators.iter().enumerate() {
                extract_ref_rows_expr(
                    value,
                    &format!("{path}/comparators[{index}]"),
                    statement_path,
                    package,
                )?;
            }
            Ok(())
        }
        ast::Expr::FormattedValue(node) => {
            extract_ref_rows_expr(
                &node.value,
                &format!("{path}/value"),
                statement_path,
                package,
            )?;
            if let Some(value) = node.format_spec.as_ref() {
                extract_ref_rows_expr(
                    value,
                    &format!("{path}/format_spec"),
                    statement_path,
                    package,
                )?;
            }
            Ok(())
        }
        ast::Expr::JoinedStr(node) => {
            extract_ref_rows_expr_list(&node.values, path, "values", statement_path, package)
        }
        ast::Expr::ListComp(node) => {
            extract_ref_rows_expr(&node.elt, &format!("{path}/elt"), statement_path, package)?;
            extract_ref_rows_comprehensions(&node.generators, path, statement_path, package)
        }
        ast::Expr::SetComp(node) => {
            extract_ref_rows_expr(&node.elt, &format!("{path}/elt"), statement_path, package)?;
            extract_ref_rows_comprehensions(&node.generators, path, statement_path, package)
        }
        ast::Expr::GeneratorExp(node) => {
            extract_ref_rows_expr(&node.elt, &format!("{path}/elt"), statement_path, package)?;
            extract_ref_rows_comprehensions(&node.generators, path, statement_path, package)
        }
        ast::Expr::DictComp(node) => {
            extract_ref_rows_expr(&node.key, &format!("{path}/key"), statement_path, package)?;
            extract_ref_rows_expr(
                &node.value,
                &format!("{path}/value"),
                statement_path,
                package,
            )?;
            extract_ref_rows_comprehensions(&node.generators, path, statement_path, package)
        }
        ast::Expr::Await(node) => extract_ref_rows_expr(
            &node.value,
            &format!("{path}/value"),
            statement_path,
            package,
        ),
        ast::Expr::Yield(node) => {
            if let Some(value) = node.value.as_ref() {
                extract_ref_rows_expr(value, &format!("{path}/value"), statement_path, package)?;
            }
            Ok(())
        }
        ast::Expr::YieldFrom(node) => extract_ref_rows_expr(
            &node.value,
            &format!("{path}/value"),
            statement_path,
            package,
        ),
        ast::Expr::Slice(node) => {
            if let Some(value) = node.lower.as_ref() {
                extract_ref_rows_expr(value, &format!("{path}/lower"), statement_path, package)?;
            }
            if let Some(value) = node.upper.as_ref() {
                extract_ref_rows_expr(value, &format!("{path}/upper"), statement_path, package)?;
            }
            if let Some(value) = node.step.as_ref() {
                extract_ref_rows_expr(value, &format!("{path}/step"), statement_path, package)?;
            }
            Ok(())
        }
        ast::Expr::Constant(_) | ast::Expr::Name(_) => Ok(()),
    }
}

fn extract_ref_rows_expr_list(
    values: &[ast::Expr],
    path: &str,
    field: &str,
    statement_path: Option<&str>,
    package: &mut PackageBuilder,
) -> PyResult<()> {
    for (index, value) in values.iter().enumerate() {
        extract_ref_rows_expr(
            value,
            &format!("{path}/{field}[{index}]"),
            statement_path,
            package,
        )?;
    }
    Ok(())
}

fn extract_ref_rows_comprehensions(
    comprehensions: &[ast::Comprehension],
    path: &str,
    statement_path: Option<&str>,
    package: &mut PackageBuilder,
) -> PyResult<()> {
    for (index, comprehension) in comprehensions.iter().enumerate() {
        extract_ref_rows_expr(
            &comprehension.target,
            &format!("{path}/generators[{index}]/target"),
            statement_path,
            package,
        )?;
        extract_ref_rows_expr(
            &comprehension.iter,
            &format!("{path}/generators[{index}]/iter"),
            statement_path,
            package,
        )?;
        for (if_index, condition) in comprehension.ifs.iter().enumerate() {
            extract_ref_rows_expr(
                condition,
                &format!("{path}/generators[{index}]/ifs[{if_index}]"),
                statement_path,
                package,
            )?;
        }
    }
    Ok(())
}

fn add_unroll_row(
    node: &ast::StmtFor,
    statement_path: &str,
    iter_path: &str,
    package: &mut PackageBuilder,
) -> PyResult<()> {
    let ast::Expr::Call(call) = &*node.iter else {
        return Ok(());
    };
    let marker_id = package.marker_id_for("astichi_for", iter_path)?;
    let domain = if call.args.len() == 1 {
        call.args.first()
    } else {
        None
    };
    let target_bindings = target_binding_names(&node.target);
    let domain_ast_path = if domain.is_some() {
        format!("{iter_path}/args[0]")
    } else {
        String::new()
    };
    let orelse_path = if node.orelse.is_empty() {
        None
    } else {
        Some(format!("{statement_path}/orelse"))
    };
    package.add_unroll_marker(
        marker_id,
        statement_path,
        &format!("{statement_path}/target"),
        iter_path,
        &domain_ast_path,
        &format!("{statement_path}/body"),
        orelse_path.as_deref(),
        target_bindings.clone(),
        domain.map(domain_shape).unwrap_or(""),
        unroll_marker_flags(node, domain, !target_bindings.is_empty()),
    );
    Ok(())
}

fn target_binding_names(target: &ast::Expr) -> Vec<String> {
    let mut names = BTreeSet::new();
    collect_target_bindings(target, &mut names);
    names.into_iter().collect()
}

fn unroll_marker_flags(
    node: &ast::StmtFor,
    domain: Option<&ast::Expr>,
    has_target_bindings: bool,
) -> Vec<String> {
    let mut flags = vec!["statement_context".to_string(), "for_statement".to_string()];
    if !node.orelse.is_empty() {
        flags.push("has_else".to_string());
    }
    let ast::Expr::Call(call) = &*node.iter else {
        return flags;
    };
    if domain.is_none() || !call.keywords.is_empty() {
        flags.push("invalid_signature".to_string());
    }
    if has_target_bindings {
        flags.push("simple_target".to_string());
    } else {
        flags.push("unsupported_target".to_string());
    }
    if domain.map(is_literal_unroll_domain).unwrap_or(false) {
        flags.push("literal_domain".to_string());
    } else if matches!(domain, Some(ast::Expr::Name(_))) {
        flags.push("external_domain_candidate".to_string());
    }
    flags
}

fn is_literal_unroll_domain(expr: &ast::Expr) -> bool {
    matches!(expr, ast::Expr::Tuple(_) | ast::Expr::List(_)) || is_range_domain(expr)
}

fn is_range_domain(expr: &ast::Expr) -> bool {
    match expr {
        ast::Expr::Call(node) => astichi_call_name(&node.func) == Some("range"),
        _ => false,
    }
}

fn domain_shape(expr: &ast::Expr) -> &'static str {
    match expr {
        ast::Expr::Tuple(_) => "tuple",
        ast::Expr::List(_) => "list",
        ast::Expr::Name(_) => "name",
        ast::Expr::Call(node) if astichi_call_name(&node.func) == Some("range") => "range",
        ast::Expr::Call(_) => "call",
        ast::Expr::BoolOp(_) => "BoolOp",
        ast::Expr::NamedExpr(_) => "NamedExpr",
        ast::Expr::BinOp(_) => "BinOp",
        ast::Expr::UnaryOp(_) => "UnaryOp",
        ast::Expr::Lambda(_) => "Lambda",
        ast::Expr::IfExp(_) => "IfExp",
        ast::Expr::Dict(_) => "Dict",
        ast::Expr::Set(_) => "Set",
        ast::Expr::Attribute(_) => "Attribute",
        ast::Expr::Subscript(_) => "Subscript",
        ast::Expr::Starred(_) => "Starred",
        ast::Expr::Compare(_) => "Compare",
        ast::Expr::FormattedValue(_) => "FormattedValue",
        ast::Expr::JoinedStr(_) => "JoinedStr",
        ast::Expr::Constant(_) => "Constant",
        ast::Expr::ListComp(_) => "ListComp",
        ast::Expr::SetComp(_) => "SetComp",
        ast::Expr::GeneratorExp(_) => "GeneratorExp",
        ast::Expr::DictComp(_) => "DictComp",
        ast::Expr::Await(_) => "Await",
        ast::Expr::Yield(_) => "Yield",
        ast::Expr::YieldFrom(_) => "YieldFrom",
        ast::Expr::Slice(_) => "Slice",
    }
}

fn is_ref_sentinel_attr(node: &ast::ExprAttribute) -> bool {
    matches!(node.attr.as_str(), "_" | "astichi_v")
        && call_expr_name(&node.value) == Some("astichi_ref")
}

fn is_ref_statement_expr(expr: &ast::Expr) -> bool {
    if call_expr_name(expr) == Some("astichi_ref") {
        return true;
    }
    match expr {
        ast::Expr::Attribute(node) => is_ref_sentinel_attr(node),
        _ => false,
    }
}

fn literal_ref_path(node: &ast::ExprCall) -> Option<Vec<String>> {
    if node.args.len() != 1 || !node.keywords.is_empty() {
        return None;
    }
    let raw = match node.args.first()? {
        ast::Expr::Constant(constant) => match &constant.value {
            ast::Constant::Str(value) => value.to_string(),
            _ => return None,
        },
        _ => return None,
    };
    validate_dotted_path(&raw)
}

fn validate_dotted_path(raw: &str) -> Option<Vec<String>> {
    let parts = raw.split('.').map(str::to_string).collect::<Vec<String>>();
    if parts.is_empty() || parts.iter().any(|part| !is_ascii_identifier(part)) {
        return None;
    }
    Some(parts)
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

fn expr_context_name(ctx: ast::ExprContext) -> &'static str {
    match ctx {
        ast::ExprContext::Load => "load",
        ast::ExprContext::Store => "store",
        ast::ExprContext::Del => "delete",
    }
}

struct MarkerState {
    source_order: usize,
    pending_pyimports: Vec<PendingPyImportMarker>,
    pending_comments: Vec<PendingCommentMarker>,
}

impl MarkerState {
    fn new() -> Self {
        Self {
            source_order: 0,
            pending_pyimports: Vec::new(),
            pending_comments: Vec::new(),
        }
    }
}

struct PendingPyImportMarker {
    marker_id: usize,
    source_order: usize,
    scope_id: usize,
    module_path: Option<Vec<String>>,
    names: Vec<String>,
    as_name: Option<String>,
    flags: Vec<String>,
}

struct PendingCommentMarker {
    marker_id: usize,
    payload: String,
}

#[derive(Clone, Copy)]
enum SuffixMarkerContext {
    Definitional,
    Identifier,
}

#[derive(Clone, Copy)]
struct SuffixMarkerSpec {
    source_name: &'static str,
    marker_kind: &'static str,
    metadata_marker: bool,
}

fn visit_stmt_markers(
    stmt: &ast::Stmt,
    path: &str,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    match stmt {
        ast::Stmt::Import(node) => {
            for (index, alias) in node.names.iter().enumerate() {
                append_alias_suffix_markers(
                    alias,
                    &format!("{path}/names[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                );
            }
            Ok(())
        }
        ast::Stmt::ImportFrom(node) => {
            if let Some(module) = node.module.as_ref() {
                for segment in module.as_str().split('.') {
                    if append_suffix_identifier_marker(
                        segment,
                        path,
                        Some(path),
                        SuffixMarkerContext::Identifier,
                        scopes,
                        package,
                        marker_state,
                        false,
                    ) {
                        break;
                    }
                }
            }
            for (index, alias) in node.names.iter().enumerate() {
                append_alias_suffix_markers(
                    alias,
                    &format!("{path}/names[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                );
            }
            Ok(())
        }
        ast::Stmt::Expr(node) => visit_expr_markers(
            &node.value,
            &format!("{path}/value"),
            Some(path),
            scopes,
            package,
            marker_state,
        ),
        ast::Stmt::Assign(node) => {
            for (index, target) in node.targets.iter().enumerate() {
                visit_expr_markers(
                    target,
                    &format!("{path}/targets[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            visit_expr_markers(
                &node.value,
                &format!("{path}/value"),
                Some(path),
                scopes,
                package,
                marker_state,
            )
        }
        ast::Stmt::AnnAssign(node) => {
            visit_expr_markers(
                &node.target,
                &format!("{path}/target"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.annotation,
                &format!("{path}/annotation"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            if let Some(value) = node.value.as_ref() {
                visit_expr_markers(
                    value,
                    &format!("{path}/value"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Stmt::AugAssign(node) => {
            visit_expr_markers(
                &node.target,
                &format!("{path}/target"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.value,
                &format!("{path}/value"),
                Some(path),
                scopes,
                package,
                marker_state,
            )
        }
        ast::Stmt::Delete(node) => {
            for (index, target) in node.targets.iter().enumerate() {
                visit_expr_markers(
                    target,
                    &format!("{path}/targets[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Return(node) => {
            if let Some(value) = node.value.as_ref() {
                visit_expr_markers(
                    value,
                    &format!("{path}/value"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Assert(node) => {
            visit_expr_markers(
                &node.test,
                &format!("{path}/test"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            if let Some(msg) = node.msg.as_ref() {
                visit_expr_markers(
                    msg,
                    &format!("{path}/msg"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Raise(node) => {
            if let Some(exc) = node.exc.as_ref() {
                visit_expr_markers(
                    exc,
                    &format!("{path}/exc"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            if let Some(cause) = node.cause.as_ref() {
                visit_expr_markers(
                    cause,
                    &format!("{path}/cause"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Stmt::For(node) => {
            visit_expr_markers(
                &node.target,
                &format!("{path}/target"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.iter,
                &format!("{path}/iter"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.body,
                &format!("{path}/body"),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.orelse,
                &format!("{path}/orelse"),
                scopes,
                package,
                marker_state,
            )
        }
        ast::Stmt::While(node) => {
            visit_expr_markers(
                &node.test,
                &format!("{path}/test"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.body,
                &format!("{path}/body"),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.orelse,
                &format!("{path}/orelse"),
                scopes,
                package,
                marker_state,
            )
        }
        ast::Stmt::If(node) => {
            visit_expr_markers(
                &node.test,
                &format!("{path}/test"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.body,
                &format!("{path}/body"),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.orelse,
                &format!("{path}/orelse"),
                scopes,
                package,
                marker_state,
            )
        }
        ast::Stmt::With(node) => {
            if let Some(item) = node.items.first() {
                if let ast::Expr::Call(call) = &item.context_expr {
                    if call_name(&call.func) == Some("astichi_hole") {
                        append_marker_for_call(
                            "astichi_hole",
                            call,
                            path,
                            Some(path),
                            scopes,
                            package,
                            marker_state,
                        )?;
                        return Ok(());
                    }
                }
            }
            for (index, item) in node.items.iter().enumerate() {
                visit_expr_markers(
                    &item.context_expr,
                    &format!("{path}/items[{index}]/context_expr"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
                if let Some(optional_vars) = item.optional_vars.as_ref() {
                    visit_expr_markers(
                        optional_vars,
                        &format!("{path}/items[{index}]/optional_vars"),
                        Some(path),
                        scopes,
                        package,
                        marker_state,
                    )?;
                }
            }
            visit_stmt_list_markers(
                &node.body,
                &format!("{path}/body"),
                scopes,
                package,
                marker_state,
            )
        }
        ast::Stmt::FunctionDef(node) => {
            append_definitional_payload_marker(
                node.name.as_str(),
                path,
                Some(path),
                scopes,
                package,
                marker_state,
            );
            append_suffix_identifier_marker(
                node.name.as_str(),
                path,
                Some(path),
                SuffixMarkerContext::Definitional,
                scopes,
                package,
                marker_state,
                false,
            );
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                append_decorator_marker_for_expr(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            visit_arguments_markers(
                &node.args,
                &format!("{path}/args"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.body,
                &format!("{path}/body"),
                scopes,
                package,
                marker_state,
            )?;
            if let Some(returns) = node.returns.as_ref() {
                visit_expr_markers(
                    returns,
                    &format!("{path}/returns"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                visit_expr_markers(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            append_definitional_payload_marker(
                node.name.as_str(),
                path,
                Some(path),
                scopes,
                package,
                marker_state,
            );
            append_suffix_identifier_marker(
                node.name.as_str(),
                path,
                Some(path),
                SuffixMarkerContext::Definitional,
                scopes,
                package,
                marker_state,
                false,
            );
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                append_decorator_marker_for_expr(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            visit_arguments_markers(
                &node.args,
                &format!("{path}/args"),
                Some(path),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.body,
                &format!("{path}/body"),
                scopes,
                package,
                marker_state,
            )?;
            if let Some(returns) = node.returns.as_ref() {
                visit_expr_markers(
                    returns,
                    &format!("{path}/returns"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                visit_expr_markers(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Stmt::ClassDef(node) => {
            append_suffix_identifier_marker(
                node.name.as_str(),
                path,
                Some(path),
                SuffixMarkerContext::Definitional,
                scopes,
                package,
                marker_state,
                false,
            );
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                append_decorator_marker_for_expr(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            for (index, base) in node.bases.iter().enumerate() {
                visit_expr_markers(
                    base,
                    &format!("{path}/bases[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            for (index, keyword) in node.keywords.iter().enumerate() {
                if let Some(arg) = keyword.arg.as_ref() {
                    append_suffix_identifier_marker(
                        arg.as_str(),
                        &format!("{path}/keywords[{index}]"),
                        Some(path),
                        SuffixMarkerContext::Identifier,
                        scopes,
                        package,
                        marker_state,
                        false,
                    );
                }
                visit_expr_markers(
                    &keyword.value,
                    &format!("{path}/keywords[{index}]/value"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            visit_stmt_list_markers(
                &node.body,
                &format!("{path}/body"),
                scopes,
                package,
                marker_state,
            )?;
            for (index, decorator) in node.decorator_list.iter().enumerate() {
                visit_expr_markers(
                    decorator,
                    &format!("{path}/decorator_list[{index}]"),
                    Some(path),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Stmt::Try(node) => {
            visit_stmt_list_markers(
                &node.body,
                &format!("{path}/body"),
                scopes,
                package,
                marker_state,
            )?;
            for (index, handler) in node.handlers.iter().enumerate() {
                let ast::ExceptHandler::ExceptHandler(handler) = handler;
                if let Some(type_) = handler.type_.as_ref() {
                    visit_expr_markers(
                        type_,
                        &format!("{path}/handlers[{index}]/type"),
                        Some(path),
                        scopes,
                        package,
                        marker_state,
                    )?;
                }
                visit_stmt_list_markers(
                    &handler.body,
                    &format!("{path}/handlers[{index}]/body"),
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            visit_stmt_list_markers(
                &node.orelse,
                &format!("{path}/orelse"),
                scopes,
                package,
                marker_state,
            )?;
            visit_stmt_list_markers(
                &node.finalbody,
                &format!("{path}/finalbody"),
                scopes,
                package,
                marker_state,
            )
        }
        _ => Ok(()),
    }
}

fn visit_stmt_list_markers(
    body: &[ast::Stmt],
    parent_path: &str,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    for (index, stmt) in body.iter().enumerate() {
        visit_stmt_markers(
            stmt,
            &format!("{parent_path}[{index}]"),
            scopes,
            package,
            marker_state,
        )?;
    }
    Ok(())
}

fn visit_arguments_markers(
    args: &ast::Arguments,
    path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    let mut default_index = 0usize;
    for (index, arg) in args.posonlyargs.iter().enumerate() {
        visit_arg_markers(
            &arg.def,
            &format!("{path}/posonlyargs[{index}]"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
        if let Some(default) = arg.default.as_ref() {
            visit_expr_markers(
                default,
                &format!("{path}/defaults[{default_index}]"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            default_index += 1;
        }
    }
    for (index, arg) in args.args.iter().enumerate() {
        visit_arg_markers(
            &arg.def,
            &format!("{path}/args[{index}]"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
        if let Some(default) = arg.default.as_ref() {
            visit_expr_markers(
                default,
                &format!("{path}/defaults[{default_index}]"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            default_index += 1;
        }
    }
    if let Some(arg) = args.vararg.as_ref() {
        visit_arg_markers(
            arg,
            &format!("{path}/vararg"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
    }
    for (index, arg) in args.kwonlyargs.iter().enumerate() {
        visit_arg_markers(
            &arg.def,
            &format!("{path}/kwonlyargs[{index}]"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
        if let Some(default) = arg.default.as_ref() {
            visit_expr_markers(
                default,
                &format!("{path}/kw_defaults[{index}]"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
        }
    }
    if let Some(arg) = args.kwarg.as_ref() {
        visit_arg_markers(
            arg,
            &format!("{path}/kwarg"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
    }
    Ok(())
}

fn visit_arg_markers(
    arg: &ast::Arg,
    path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    append_suffix_identifier_marker(
        arg.arg.as_str(),
        path,
        statement_path,
        SuffixMarkerContext::Identifier,
        scopes,
        package,
        marker_state,
        true,
    );
    if let Some(annotation) = arg.annotation.as_ref() {
        visit_expr_markers(
            annotation,
            &format!("{path}/annotation"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
    }
    Ok(())
}

fn visit_expr_markers(
    expr: &ast::Expr,
    path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    match expr {
        ast::Expr::Call(node) => {
            if let Some(source_name) = call_name(&node.func) {
                append_marker_for_call(
                    source_name,
                    node,
                    path,
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            visit_expr_markers(
                &node.func,
                &format!("{path}/func"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            for (index, arg) in node.args.iter().enumerate() {
                visit_expr_markers(
                    arg,
                    &format!("{path}/args[{index}]"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            for (index, keyword) in node.keywords.iter().enumerate() {
                if let Some(arg) = keyword.arg.as_ref() {
                    append_suffix_identifier_marker(
                        arg.as_str(),
                        &format!("{path}/keywords[{index}]"),
                        statement_path,
                        SuffixMarkerContext::Identifier,
                        scopes,
                        package,
                        marker_state,
                        false,
                    );
                }
                visit_expr_markers(
                    &keyword.value,
                    &format!("{path}/keywords[{index}]/value"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
                if astichi_call_name(&node.func) == Some("astichi_ref")
                    && keyword.arg.as_ref().map(|arg| arg.as_str()) == Some("external")
                {
                    append_external_ref_bind_marker(
                        &keyword.value,
                        &format!("{path}/args[0]"),
                        statement_path,
                        scopes,
                        package,
                        marker_state,
                    );
                }
            }
            Ok(())
        }
        ast::Expr::BoolOp(node) => {
            for (index, value) in node.values.iter().enumerate() {
                visit_expr_markers(
                    value,
                    &format!("{path}/values[{index}]"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Expr::NamedExpr(node) => {
            visit_expr_markers(
                &node.target,
                &format!("{path}/target"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.value,
                &format!("{path}/value"),
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::BinOp(node) => {
            visit_expr_markers(
                &node.left,
                &format!("{path}/left"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.right,
                &format!("{path}/right"),
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::UnaryOp(node) => visit_expr_markers(
            &node.operand,
            &format!("{path}/operand"),
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::Lambda(node) => {
            visit_arguments_markers(
                &node.args,
                &format!("{path}/args"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.body,
                &format!("{path}/body"),
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::IfExp(node) => {
            visit_expr_markers(
                &node.test,
                &format!("{path}/test"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.body,
                &format!("{path}/body"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.orelse,
                &format!("{path}/orelse"),
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::Dict(node) => {
            for (index, key) in node.keys.iter().enumerate() {
                if let Some(key) = key {
                    visit_expr_markers(
                        key,
                        &format!("{path}/keys[{index}]"),
                        statement_path,
                        scopes,
                        package,
                        marker_state,
                    )?;
                }
            }
            for (index, value) in node.values.iter().enumerate() {
                visit_expr_markers(
                    value,
                    &format!("{path}/values[{index}]"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Expr::Set(node) => visit_expr_list_markers(
            &node.elts,
            path,
            "elts",
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::List(node) => visit_expr_list_markers(
            &node.elts,
            path,
            "elts",
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::Tuple(node) => visit_expr_list_markers(
            &node.elts,
            path,
            "elts",
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::Attribute(node) => visit_expr_markers(
            &node.value,
            &format!("{path}/value"),
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::Subscript(node) => {
            visit_expr_markers(
                &node.value,
                &format!("{path}/value"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.slice,
                &format!("{path}/slice"),
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::Starred(node) => visit_expr_markers(
            &node.value,
            &format!("{path}/value"),
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::Compare(node) => {
            visit_expr_markers(
                &node.left,
                &format!("{path}/left"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            for (index, value) in node.comparators.iter().enumerate() {
                visit_expr_markers(
                    value,
                    &format!("{path}/comparators[{index}]"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Expr::FormattedValue(node) => {
            visit_expr_markers(
                &node.value,
                &format!("{path}/value"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            if let Some(value) = node.format_spec.as_ref() {
                visit_expr_markers(
                    value,
                    &format!("{path}/format_spec"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Expr::JoinedStr(node) => visit_expr_list_markers(
            &node.values,
            path,
            "values",
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::ListComp(node) => {
            visit_expr_markers(
                &node.elt,
                &format!("{path}/elt"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_comprehension_markers(
                &node.generators,
                path,
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::SetComp(node) => {
            visit_expr_markers(
                &node.elt,
                &format!("{path}/elt"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_comprehension_markers(
                &node.generators,
                path,
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::GeneratorExp(node) => {
            visit_expr_markers(
                &node.elt,
                &format!("{path}/elt"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_comprehension_markers(
                &node.generators,
                path,
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::DictComp(node) => {
            visit_expr_markers(
                &node.key,
                &format!("{path}/key"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_expr_markers(
                &node.value,
                &format!("{path}/value"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
            visit_comprehension_markers(
                &node.generators,
                path,
                statement_path,
                scopes,
                package,
                marker_state,
            )
        }
        ast::Expr::Await(node) => visit_expr_markers(
            &node.value,
            &format!("{path}/value"),
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::Yield(node) => {
            if let Some(value) = node.value.as_ref() {
                visit_expr_markers(
                    value,
                    &format!("{path}/value"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Expr::YieldFrom(node) => visit_expr_markers(
            &node.value,
            &format!("{path}/value"),
            statement_path,
            scopes,
            package,
            marker_state,
        ),
        ast::Expr::Slice(node) => {
            if let Some(value) = node.lower.as_ref() {
                visit_expr_markers(
                    value,
                    &format!("{path}/lower"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            if let Some(value) = node.upper.as_ref() {
                visit_expr_markers(
                    value,
                    &format!("{path}/upper"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            if let Some(value) = node.step.as_ref() {
                visit_expr_markers(
                    value,
                    &format!("{path}/step"),
                    statement_path,
                    scopes,
                    package,
                    marker_state,
                )?;
            }
            Ok(())
        }
        ast::Expr::Name(node) => {
            append_suffix_identifier_marker(
                node.id.as_str(),
                path,
                statement_path,
                SuffixMarkerContext::Identifier,
                scopes,
                package,
                marker_state,
                false,
            );
            Ok(())
        }
        ast::Expr::Constant(_) => Ok(()),
    }
}

fn visit_expr_list_markers(
    values: &[ast::Expr],
    path: &str,
    field: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    for (index, value) in values.iter().enumerate() {
        visit_expr_markers(
            value,
            &format!("{path}/{field}[{index}]"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
    }
    Ok(())
}

fn visit_comprehension_markers(
    comprehensions: &[ast::Comprehension],
    path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    for (index, comprehension) in comprehensions.iter().enumerate() {
        visit_expr_markers(
            &comprehension.target,
            &format!("{path}/generators[{index}]/target"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
        visit_expr_markers(
            &comprehension.iter,
            &format!("{path}/generators[{index}]/iter"),
            statement_path,
            scopes,
            package,
            marker_state,
        )?;
        for (if_index, condition) in comprehension.ifs.iter().enumerate() {
            visit_expr_markers(
                condition,
                &format!("{path}/generators[{index}]/ifs[{if_index}]"),
                statement_path,
                scopes,
                package,
                marker_state,
            )?;
        }
    }
    Ok(())
}

fn append_marker_for_call(
    source_name: &str,
    node: &ast::ExprCall,
    ast_path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    if !is_package_marker(source_name) {
        return Ok(());
    }
    if source_name == "astichi_insert" && node.args.len() != 2 {
        return Ok(());
    }
    let scope = scope_for_ast_path(scopes, ast_path);
    let mut flags = vec!["call_context".to_string()];
    if statement_path == Some(ast_path) {
        flags.push("is_statement_marker".to_string());
    }
    if source_name == "astichi_keep" {
        flags.push("is_metadata_marker".to_string());
    }
    if matches!(source_name, "astichi_import" | "astichi_pass") {
        if boundary_keyword_bool(node, "bound")? {
            flags.push("explicit_bind_enabled".to_string());
        }
        if boundary_keyword_bool(node, "outer_bind")? {
            flags.push("outer_bind_enabled".to_string());
        }
    }
    let marker_id = package.add_marker(
        marker_state.source_order,
        marker_kind(source_name),
        source_name,
        ast_path,
        statement_path,
        scope,
        &marker_resource_name(source_name, node),
        flags,
    );
    if source_name == "astichi_pyimport" {
        let (module_path, names, as_name, flags) = pyimport_marker_payload(node);
        marker_state.pending_pyimports.push(PendingPyImportMarker {
            marker_id,
            source_order: marker_state.source_order,
            scope_id: scope.scope_id,
            module_path,
            names,
            as_name,
            flags,
        });
    } else if source_name == "astichi_comment" {
        if let Some(payload) = string_arg(node, 0) {
            marker_state
                .pending_comments
                .push(PendingCommentMarker { marker_id, payload });
        }
    }
    marker_state.source_order += 1;
    Ok(())
}

fn append_decorator_marker_for_expr(
    expr: &ast::Expr,
    ast_path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> PyResult<()> {
    let ast::Expr::Call(node) = expr else {
        return Ok(());
    };
    if call_name(&node.func) != Some("astichi_insert") || node.args.len() != 1 {
        return Ok(());
    }
    let scope = scope_for_ast_path(scopes, ast_path);
    package.add_marker(
        marker_state.source_order,
        "insert",
        "astichi_insert",
        ast_path,
        statement_path,
        scope,
        &marker_resource_name("astichi_insert", node),
        vec!["decorator_context".to_string()],
    );
    marker_state.source_order += 1;
    Ok(())
}

fn append_external_ref_bind_marker(
    expr: &ast::Expr,
    ast_path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) {
    let Some(resource_name) = name_expr(expr) else {
        return;
    };
    let scope = scope_for_ast_path(scopes, ast_path);
    package.add_marker(
        marker_state.source_order,
        "bind_external",
        "astichi_bind_external",
        ast_path,
        statement_path,
        scope,
        &resource_name,
        vec!["call_context".to_string()],
    );
    marker_state.source_order += 1;
}

fn append_alias_suffix_markers(
    alias: &ast::Alias,
    ast_path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) {
    append_suffix_identifier_marker(
        alias.name.as_str(),
        ast_path,
        statement_path,
        SuffixMarkerContext::Identifier,
        scopes,
        package,
        marker_state,
        false,
    );
    if let Some(asname) = alias.asname.as_ref() {
        append_suffix_identifier_marker(
            asname.as_str(),
            ast_path,
            statement_path,
            SuffixMarkerContext::Identifier,
            scopes,
            package,
            marker_state,
            false,
        );
    }
}

fn append_definitional_payload_marker(
    name: &str,
    ast_path: &str,
    statement_path: Option<&str>,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
) -> bool {
    let marker_kind = match name {
        "astichi_params" => "params",
        "astichi_elif" => "elif",
        _ => return false,
    };
    let scope = scope_for_ast_path(scopes, ast_path);
    let mut flags = vec!["definitional_context".to_string()];
    if statement_path == Some(ast_path) {
        flags.push("is_statement_marker".to_string());
    }
    package.add_marker(
        marker_state.source_order,
        marker_kind,
        name,
        ast_path,
        statement_path,
        scope,
        name,
        flags,
    );
    marker_state.source_order += 1;
    true
}

fn append_suffix_identifier_marker(
    name: &str,
    ast_path: &str,
    statement_path: Option<&str>,
    context: SuffixMarkerContext,
    scopes: &[ScopeSpec],
    package: &mut PackageBuilder,
    marker_state: &mut MarkerState,
    allow_param_hole: bool,
) -> bool {
    let Some((spec, resource_name)) = suffix_marker_spec(name, allow_param_hole) else {
        return false;
    };
    let scope = scope_for_ast_path(scopes, ast_path);
    let mut flags = Vec::new();
    match context {
        SuffixMarkerContext::Definitional => flags.push("definitional_context".to_string()),
        SuffixMarkerContext::Identifier => flags.push("identifier_context".to_string()),
    }
    if statement_path == Some(ast_path) {
        flags.push("is_statement_marker".to_string());
    }
    if spec.metadata_marker {
        flags.push("is_metadata_marker".to_string());
    }
    package.add_marker(
        marker_state.source_order,
        spec.marker_kind,
        spec.source_name,
        ast_path,
        statement_path,
        scope,
        &resource_name,
        flags,
    );
    marker_state.source_order += 1;
    true
}

fn suffix_marker_spec(
    name: &str,
    allow_param_hole: bool,
) -> Option<(SuffixMarkerSpec, String)> {
    if let Some(base) = valid_suffix_base(name, ARG_SUFFIX) {
        return Some((
            SuffixMarkerSpec {
                source_name: "astichi_arg_identifier",
                marker_kind: "arg_identifier",
                metadata_marker: true,
            },
            base,
        ));
    }
    if let Some(base) = valid_suffix_base(name, KEEP_SUFFIX) {
        return Some((
            SuffixMarkerSpec {
                source_name: "astichi_keep_identifier",
                marker_kind: "keep_identifier",
                metadata_marker: true,
            },
            base,
        ));
    }
    if allow_param_hole {
        if let Some(base) = valid_suffix_base(name, PARAM_HOLE_SUFFIX) {
            return Some((
                SuffixMarkerSpec {
                    source_name: "astichi_param_hole_identifier",
                    marker_kind: "param_hole_identifier",
                    metadata_marker: false,
                },
                base,
            ));
        }
    }
    None
}

fn valid_suffix_base(name: &str, suffix: &str) -> Option<String> {
    let base = name.strip_suffix(suffix)?;
    if is_ascii_identifier(base) {
        Some(base.to_string())
    } else {
        None
    }
}

fn is_package_marker(source_name: &str) -> bool {
    matches!(
        source_name,
        "astichi_hole"
            | "astichi_bind_external"
            | "astichi_ref"
            | "astichi_export"
            | "astichi_import"
            | "astichi_pass"
            | "astichi_insert"
            | "astichi_comment"
            | "astichi_funcargs"
            | "astichi_keep"
            | "astichi_pyimport"
            | "astichi_for"
            | "astichi_elif"
    )
}

fn marker_kind(source_name: &str) -> &str {
    match source_name {
        "astichi_pyimport" => "pyimport",
        "astichi_comment" => "comment",
        "astichi_ref" => "ref",
        "astichi_for" => "unroll",
        "astichi_elif" => "elif",
        other => other.strip_prefix("astichi_").unwrap_or(other),
    }
}

fn marker_resource_name(source_name: &str, node: &ast::ExprCall) -> String {
    match source_name {
        "astichi_hole"
        | "astichi_bind_external"
        | "astichi_export"
        | "astichi_import"
        | "astichi_pass"
        | "astichi_keep"
        | "astichi_insert"
        | "astichi_elif" => name_arg(node, 0).unwrap_or_default(),
        _ => String::new(),
    }
}

fn pyimport_marker_payload(
    node: &ast::ExprCall,
) -> (
    Option<Vec<String>>,
    Vec<String>,
    Option<String>,
    Vec<String>,
) {
    let module_path = keyword(node, "module").and_then(expr_path);
    let names = keyword(node, "names")
        .map(pyimport_names)
        .unwrap_or_default();
    let as_name = keyword(node, "as_").and_then(name_expr);
    let mut flags = Vec::new();
    if !names.is_empty() {
        flags.push("from_import".to_string());
    } else {
        flags.push("plain_import".to_string());
    }
    if module_path.is_none() {
        flags.push("dynamic_module".to_string());
    }
    (module_path, names, as_name, flags)
}

fn pyimport_names(expr: &ast::Expr) -> Vec<String> {
    match expr {
        ast::Expr::Tuple(node) => node.elts.iter().filter_map(name_expr).collect(),
        ast::Expr::List(node) => node.elts.iter().filter_map(name_expr).collect(),
        ast::Expr::Name(node) => vec![node.id.to_string()],
        _ => Vec::new(),
    }
}

fn expr_path(expr: &ast::Expr) -> Option<Vec<String>> {
    match expr {
        ast::Expr::Name(node) => Some(vec![node.id.to_string()]),
        ast::Expr::Attribute(node) => {
            let mut path = expr_path(&node.value)?;
            path.push(node.attr.to_string());
            Some(path)
        }
        _ => None,
    }
}

fn name_expr(expr: &ast::Expr) -> Option<String> {
    match expr {
        ast::Expr::Name(node) => Some(node.id.to_string()),
        _ => None,
    }
}

fn name_arg(node: &ast::ExprCall, index: usize) -> Option<String> {
    node.args.get(index).and_then(name_expr)
}

fn string_arg(node: &ast::ExprCall, index: usize) -> Option<String> {
    match node.args.get(index)? {
        ast::Expr::Constant(constant) => match &constant.value {
            ast::Constant::Str(value) => Some(value.to_string()),
            _ => None,
        },
        _ => None,
    }
}

fn keyword<'a>(node: &'a ast::ExprCall, name: &str) -> Option<&'a ast::Expr> {
    node.keywords.iter().find_map(|keyword| {
        if keyword.arg.as_ref().map(|arg| arg.as_str()) == Some(name) {
            Some(&keyword.value)
        } else {
            None
        }
    })
}

fn boundary_keyword_bool(node: &ast::ExprCall, name: &str) -> PyResult<bool> {
    let Some(value) = keyword(node, name) else {
        return Ok(false);
    };
    match value {
        ast::Expr::Constant(constant) => match constant.value {
            ast::Constant::Bool(value) => Ok(value),
            _ => Err(crate::errors::schema_error(&format!(
                "boundary keyword `{name}` must be a literal True/False"
            ))),
        },
        _ => Err(crate::errors::schema_error(&format!(
            "boundary keyword `{name}` must be a literal True/False"
        ))),
    }
}

fn scope_for_ast_path<'a>(scopes: &'a [ScopeSpec], ast_path: &str) -> &'a ScopeSpec {
    let mut best = &scopes[0];
    let mut best_depth = 0;
    for scope in scopes {
        if ast_path_is_prefix(&scope.ast_path, ast_path) {
            let depth = ast_path_depth(&scope.ast_path);
            if depth >= best_depth {
                best = scope;
                best_depth = depth;
            }
        }
    }
    best
}

fn ast_path_is_prefix(scope_path: &str, ast_path: &str) -> bool {
    scope_path.is_empty()
        || ast_path == scope_path
        || ast_path.starts_with(&format!("{scope_path}/"))
}

fn ast_path_depth(ast_path: &str) -> usize {
    if ast_path.is_empty() {
        0
    } else {
        ast_path.split('/').filter(|part| !part.is_empty()).count()
    }
}

fn sorted_unique(names: &[String]) -> Vec<String> {
    names
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn call_name(expr: &ast::Expr) -> Option<&str> {
    match expr {
        ast::Expr::Name(node) => Some(node.id.as_str()),
        _ => None,
    }
}

fn astichi_call_name(expr: &ast::Expr) -> Option<&str> {
    match expr {
        ast::Expr::Name(node) => Some(node.id.as_str()),
        ast::Expr::Attribute(node) => Some(node.attr.as_str()),
        _ => None,
    }
}

fn call_expr_name(expr: &ast::Expr) -> Option<&str> {
    match expr {
        ast::Expr::Call(node) => call_name(&node.func),
        _ => None,
    }
}
