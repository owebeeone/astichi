use std::collections::{BTreeMap, BTreeSet};

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule};
use rustpython_parser::ast;

use crate::handles::EngineHandle;
use crate::surface_registry::RegisteredSurfaceBundle;
use crate::template_package_v2::PackageBuilder;

const STRUCTURAL_SCHEMA: &str = "astichi.structural-inventory.v1";
const HANDLE_KIND_TEMPLATE: &str = "template";
const HANDLE_KIND_ASSEMBLY_STATE: &str = "assembly-state";
const HANDLE_KIND_OCCURRENCE: &str = "occurrence";
const HANDLE_KIND_RECORD: &str = "record";
const HANDLE_KIND_EDGE: &str = "edge";
const HANDLE_KIND_OVERLAY: &str = "overlay";

#[derive(Clone)]
pub struct NativeTemplate {
    template_key: String,
    source_summary: String,
    locator_base: usize,
    locators: Vec<NativeLocator>,
    records: Vec<NativeTemplateRecord>,
    package_v2: Option<PackageBuilder>,
    module: Option<ast::ModModule>,
}

impl NativeTemplate {
    pub(crate) fn from_package(
        package: PackageBuilder,
        module: Option<ast::ModModule>,
        locator_base: usize,
    ) -> Self {
        let template_key = package.strings[1].clone();
        let source_summary = package.strings[2].clone();
        let locators = package
            .locators
            .iter()
            .map(|locator| NativeLocator {
                ast_path: package.ast_paths[locator.ast_path_id].clone(),
                authored_summary: package.strings[locator.authored_summary_id].clone(),
                materialization_anchor: package.strings[locator.materialization_anchor_id].clone(),
                parent_locator_id: locator.parent_locator_id,
                role_key: package.strings[locator.role_key_id].clone(),
            })
            .collect::<Vec<_>>();
        let records = package
            .records
            .iter()
            .map(|record| NativeTemplateRecord {
                code_owner: package.paths[record.owner_path_id].clone(),
                inventory_kind: package.strings[record.inventory_kind_id].clone(),
                locator_id: record.locator_id,
                resource_name: record
                    .resource_name_id
                    .map(|id| package.strings[id].clone())
                    .unwrap_or_default(),
                semantic_summary: package.strings[record.semantic_summary_id].clone(),
                surface_key: package.strings[record.surface_key_id].clone(),
            })
            .collect::<Vec<_>>();
        Self {
            template_key,
            source_summary,
            locator_base,
            locators,
            records,
            package_v2: Some(package),
            module,
        }
    }

    fn locator_base(&self) -> usize {
        self.locator_base
    }

    fn locators(&self) -> &[NativeLocator] {
        &self.locators
    }

    pub(crate) fn records(&self) -> &[NativeTemplateRecord] {
        &self.records
    }

    fn package_v2(&self) -> Option<&PackageBuilder> {
        self.package_v2.as_ref()
    }

    pub(crate) fn module(&self) -> Option<&ast::ModModule> {
        self.module.as_ref()
    }

    pub(crate) fn locator_count(&self) -> usize {
        self.locators.len()
    }

    pub(crate) fn locator_ast_path(&self, locator_id: usize) -> PyResult<&str> {
        self.locators
            .get(locator_id)
            .map(|locator| locator.ast_path.as_str())
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native locator"))
    }

    pub(crate) fn locator_ast_path_for_record(
        &self,
        template_record_index: usize,
    ) -> PyResult<&str> {
        let record = self.records.get(template_record_index).ok_or_else(|| {
            crate::errors::stale_handle_error("unknown native template record handle")
        })?;
        self.locator_ast_path(record.locator_id)
    }

    pub(crate) fn unique_locator_ast_path_for_surface(&self, surface_key: &str) -> PyResult<&str> {
        let mut matches = self
            .records
            .iter()
            .filter(|record| record.surface_key == surface_key)
            .map(|record| record.locator_id);
        let Some(locator_id) = matches.next() else {
            return Err(crate::errors::schema_error(&format!(
                "native template has no `{surface_key}` record"
            )));
        };
        if matches.next().is_some() {
            return Err(crate::errors::schema_error(&format!(
                "native template has multiple `{surface_key}` records"
            )));
        }
        self.locator_ast_path(locator_id)
    }
}

#[derive(Clone)]
struct NativeLocator {
    ast_path: String,
    authored_summary: String,
    materialization_anchor: String,
    parent_locator_id: Option<usize>,
    role_key: String,
}

#[derive(Clone)]
pub struct NativeTemplateRecord {
    code_owner: Vec<String>,
    inventory_kind: String,
    locator_id: usize,
    resource_name: String,
    semantic_summary: String,
    surface_key: String,
}

impl NativeTemplateRecord {
    pub(crate) fn resource_name(&self) -> &str {
        &self.resource_name
    }
}

#[derive(Clone)]
pub struct NativeAssemblyState {
    occurrences: Vec<NativeOccurrence>,
    edges: Vec<NativeEdge>,
    overlays: Vec<NativeOverlay>,
    indexes: NativeIndexes,
    satisfied_records: BTreeSet<RecordKey>,
    dead_records: BTreeSet<RecordKey>,
}

impl NativeAssemblyState {
    pub fn new() -> Self {
        Self {
            occurrences: Vec::new(),
            edges: Vec::new(),
            overlays: Vec::new(),
            indexes: NativeIndexes::default(),
            satisfied_records: BTreeSet::new(),
            dead_records: BTreeSet::new(),
        }
    }

    pub(crate) fn occurrence(&self, index: usize) -> PyResult<&NativeOccurrence> {
        self.occurrences
            .get(index)
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native occurrence handle"))
    }

    pub(crate) fn edge(&self, index: usize) -> PyResult<&NativeEdge> {
        self.edges
            .get(index)
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native edge handle"))
    }

    pub(crate) fn overlay(&self, index: usize) -> PyResult<&NativeOverlay> {
        self.overlays
            .get(index)
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native overlay handle"))
    }

    fn append_occurrence(
        &mut self,
        template_index: usize,
        build_path: Vec<String>,
        parent_occurrence_index: Option<usize>,
        records: &[NativeTemplateRecord],
    ) -> usize {
        let occurrence_index = self.occurrences.len();
        self.occurrences.push(NativeOccurrence {
            template_index,
            build_path: build_path.clone(),
            parent_occurrence_index,
            live: true,
        });
        for (template_record_index, record) in records.iter().enumerate() {
            self.indexes.append(
                &build_path,
                record,
                RecordKey {
                    occurrence_index,
                    template_record_index,
                },
            );
        }
        occurrence_index
    }

    fn append_edge(
        &mut self,
        target_record: RecordKey,
        source_occurrence_index: usize,
        operation_key: String,
        order: i64,
    ) -> usize {
        let edge_index = self.edges.len();
        self.edges.push(NativeEdge {
            target_record,
            source_occurrence_index,
            operation_key,
            order,
        });
        edge_index
    }

    fn append_overlay(
        &mut self,
        kind: String,
        source_label: String,
        target_record: RecordKey,
    ) -> usize {
        let overlay_index = self.overlays.len();
        self.overlays.push(NativeOverlay {
            kind,
            source_label,
            target_record,
        });
        overlay_index
    }
}

#[derive(Clone)]
pub(crate) struct NativeOccurrence {
    template_index: usize,
    build_path: Vec<String>,
    parent_occurrence_index: Option<usize>,
    live: bool,
}

impl NativeOccurrence {
    pub(crate) fn template_index(&self) -> usize {
        self.template_index
    }
}

#[derive(Clone)]
pub(crate) struct NativeEdge {
    target_record: RecordKey,
    source_occurrence_index: usize,
    operation_key: String,
    order: i64,
}

impl NativeEdge {
    pub(crate) fn target_record(&self) -> RecordKey {
        self.target_record
    }

    pub(crate) fn source_occurrence_index(&self) -> usize {
        self.source_occurrence_index
    }

    pub(crate) fn operation_key(&self) -> &str {
        &self.operation_key
    }
}

#[derive(Clone)]
pub(crate) struct NativeOverlay {
    kind: String,
    source_label: String,
    target_record: RecordKey,
}

impl NativeOverlay {
    pub(crate) fn kind(&self) -> &str {
        &self.kind
    }

    pub(crate) fn source_label(&self) -> &str {
        &self.source_label
    }

    pub(crate) fn target_record(&self) -> RecordKey {
        self.target_record
    }
}

#[derive(Clone, Default)]
struct NativeIndexes {
    by_build_path: BTreeMap<Vec<String>, Vec<RecordKey>>,
    by_surface: BTreeMap<String, Vec<RecordKey>>,
    by_resource_name: BTreeMap<String, Vec<RecordKey>>,
    by_inventory_kind: BTreeMap<String, Vec<RecordKey>>,
    by_owner: BTreeMap<Vec<String>, Vec<RecordKey>>,
    by_name_and_kind: BTreeMap<(String, String), Vec<RecordKey>>,
}

impl NativeIndexes {
    fn append(
        &mut self,
        build_path: &[String],
        record: &NativeTemplateRecord,
        record_key: RecordKey,
    ) {
        self.by_build_path
            .entry(build_path.to_vec())
            .or_default()
            .push(record_key);
        self.by_surface
            .entry(record.surface_key.clone())
            .or_default()
            .push(record_key);
        if !record.resource_name.is_empty() {
            self.by_resource_name
                .entry(record.resource_name.clone())
                .or_default()
                .push(record_key);
            if !record.inventory_kind.is_empty() {
                self.by_name_and_kind
                    .entry((record.resource_name.clone(), record.inventory_kind.clone()))
                    .or_default()
                    .push(record_key);
            }
        }
        if !record.inventory_kind.is_empty() {
            self.by_inventory_kind
                .entry(record.inventory_kind.clone())
                .or_default()
                .push(record_key);
        }
        self.by_owner
            .entry(record.code_owner.clone())
            .or_default()
            .push(record_key);
    }
}

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct RecordKey {
    occurrence_index: usize,
    template_record_index: usize,
}

impl RecordKey {
    pub(crate) fn occurrence_index(&self) -> usize {
        self.occurrence_index
    }

    pub(crate) fn template_record_index(&self) -> usize {
        self.template_record_index
    }
}

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct NativeTemplateHandle {
    owner_id: u64,
    index: usize,
    generation: u64,
}

impl NativeTemplateHandle {
    fn new(owner_id: u64, index: usize) -> Self {
        Self {
            owner_id,
            index,
            generation: 0,
        }
    }

    pub(crate) fn owner_id(&self) -> u64 {
        self.owner_id
    }

    pub(crate) fn template_index(&self) -> usize {
        self.index
    }
}

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct NativeAssemblyStateHandle {
    owner_id: u64,
    index: usize,
    generation: u64,
}

impl NativeAssemblyStateHandle {
    fn new(owner_id: u64, index: usize) -> Self {
        Self {
            owner_id,
            index,
            generation: 0,
        }
    }

    pub(crate) fn owner_id(&self) -> u64 {
        self.owner_id
    }

    pub(crate) fn state_index(&self) -> usize {
        self.index
    }
}

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct NativeOccurrenceHandle {
    owner_id: u64,
    state_index: usize,
    index: usize,
    generation: u64,
}

impl NativeOccurrenceHandle {
    fn new(owner_id: u64, state_index: usize, index: usize) -> Self {
        Self {
            owner_id,
            state_index,
            index,
            generation: 0,
        }
    }
}

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct NativeRecordHandle {
    owner_id: u64,
    state_index: usize,
    occurrence_index: usize,
    template_record_index: usize,
    generation: u64,
}

impl NativeRecordHandle {
    fn new(
        owner_id: u64,
        state_index: usize,
        occurrence_index: usize,
        template_record_index: usize,
    ) -> Self {
        Self {
            owner_id,
            state_index,
            occurrence_index,
            template_record_index,
            generation: 0,
        }
    }
}

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct NativeEdgeHandle {
    owner_id: u64,
    state_index: usize,
    index: usize,
    generation: u64,
}

impl NativeEdgeHandle {
    fn new(owner_id: u64, state_index: usize, index: usize) -> Self {
        Self {
            owner_id,
            state_index,
            index,
            generation: 0,
        }
    }

    pub(crate) fn owner_id(&self) -> u64 {
        self.owner_id
    }

    pub(crate) fn edge_state_index(&self) -> usize {
        self.state_index
    }

    pub(crate) fn edge_index(&self) -> usize {
        self.index
    }
}

#[pyclass(module = "_astichi_native_engine", skip_from_py_object)]
pub struct NativeOverlayHandle {
    owner_id: u64,
    state_index: usize,
    index: usize,
    generation: u64,
}

impl NativeOverlayHandle {
    fn new(owner_id: u64, state_index: usize, index: usize) -> Self {
        Self {
            owner_id,
            state_index,
            index,
            generation: 0,
        }
    }

    pub(crate) fn owner_id(&self) -> u64 {
        self.owner_id
    }

    pub(crate) fn overlay_state_index(&self) -> usize {
        self.state_index
    }

    pub(crate) fn overlay_index(&self) -> usize {
        self.index
    }
}

#[pyfunction(name = "register_template_snapshot")]
fn register_template_snapshot(
    mut engine: PyRefMut<'_, EngineHandle>,
    snapshot: &Bound<'_, PyDict>,
) -> PyResult<NativeTemplateHandle> {
    engine.ensure_open()?;
    if engine.surface_bundle().is_none() {
        return Err(crate::errors::schema_error(
            "surface bundle has not been registered",
        ));
    }
    validate_snapshot_schema(snapshot)?;
    let template_index = engine.template_count();
    let locator_base = engine
        .templates()
        .iter()
        .map(|template| template.locators().len())
        .sum();
    let template = parse_template_snapshot(snapshot, locator_base)?;
    let index = engine.push_template(template)?;
    debug_assert_eq!(index, template_index);
    Ok(NativeTemplateHandle::new(engine.owner_id(), index))
}

pub(crate) fn register_template_package(
    mut engine: PyRefMut<'_, EngineHandle>,
    package: PackageBuilder,
    module: Option<ast::ModModule>,
) -> PyResult<NativeTemplateHandle> {
    engine.ensure_open()?;
    if engine.surface_bundle().is_none() {
        return Err(crate::errors::schema_error(
            "surface bundle has not been registered",
        ));
    }
    let template_index = engine.template_count();
    let locator_base = engine
        .templates()
        .iter()
        .map(|template| template.locators().len())
        .sum();
    let template = NativeTemplate::from_package(package, module, locator_base);
    let index = engine.push_template(template)?;
    debug_assert_eq!(index, template_index);
    Ok(NativeTemplateHandle::new(engine.owner_id(), index))
}

pub(crate) fn template_package_v2_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    template: PyRef<'_, NativeTemplateHandle>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), template.owner_id)?;
    let template = engine.template(template.index)?;
    let package = template.package_v2().ok_or_else(|| {
        crate::errors::schema_error("native template does not carry package-v2 rows")
    })?;
    package.snapshot(py)
}

#[pyfunction(name = "assembly_state_create")]
fn assembly_state_create(
    mut engine: PyRefMut<'_, EngineHandle>,
) -> PyResult<NativeAssemblyStateHandle> {
    engine.ensure_open()?;
    let index = engine.push_state(NativeAssemblyState::new())?;
    Ok(NativeAssemblyStateHandle::new(engine.owner_id(), index))
}

#[pyfunction(name = "assembly_state_append_occurrence", signature = (engine, state, template, build_path, parent_occurrence=None))]
fn assembly_state_append_occurrence(
    mut engine: PyRefMut<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    template: PyRef<'_, NativeTemplateHandle>,
    build_path: &Bound<'_, PyAny>,
    parent_occurrence: Option<PyRef<'_, NativeOccurrenceHandle>>,
) -> PyResult<NativeOccurrenceHandle> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    ensure_owner(engine.owner_id(), template.owner_id)?;
    let build_path = parse_string_sequence(build_path, "build_path")?;
    let template_index = template.index;
    let records = engine.template(template_index)?.records().to_vec();
    let parent_occurrence_index = match parent_occurrence.as_ref() {
        Some(parent) => {
            ensure_owner(engine.owner_id(), parent.owner_id)?;
            if parent.state_index != state.index {
                return Err(crate::errors::stale_handle_error(
                    "parent occurrence belongs to another native assembly state",
                ));
            }
            let state_ref = engine.state(state.index)?;
            state_ref.occurrence(parent.index)?;
            Some(parent.index)
        }
        None => None,
    };
    let owner_id = engine.owner_id();
    let state_index = state.index;
    let state_ref = engine.state_mut(state.index)?;
    let occurrence_index = state_ref.append_occurrence(
        template_index,
        build_path,
        parent_occurrence_index,
        &records,
    );
    Ok(NativeOccurrenceHandle::new(
        owner_id,
        state_index,
        occurrence_index,
    ))
}

#[pyfunction(name = "assembly_state_record_handle")]
fn assembly_state_record_handle(
    engine: PyRef<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    occurrence: PyRef<'_, NativeOccurrenceHandle>,
    template_record_index: usize,
) -> PyResult<NativeRecordHandle> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    ensure_owner(engine.owner_id(), occurrence.owner_id)?;
    if occurrence.state_index != state.index {
        return Err(crate::errors::stale_handle_error(
            "occurrence belongs to another native assembly state",
        ));
    }
    let state_ref = engine.state(state.index)?;
    let occurrence_ref = state_ref.occurrence(occurrence.index)?;
    let template = engine.template(occurrence_ref.template_index)?;
    if template_record_index >= template.records().len() {
        return Err(crate::errors::stale_handle_error(
            "unknown native template record handle",
        ));
    }
    Ok(NativeRecordHandle::new(
        engine.owner_id(),
        state.index,
        occurrence.index,
        template_record_index,
    ))
}

#[pyfunction(name = "assembly_state_append_edge")]
fn assembly_state_append_edge(
    mut engine: PyRefMut<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    target: PyRef<'_, NativeRecordHandle>,
    source: PyRef<'_, NativeOccurrenceHandle>,
    operation_key: String,
    order: i64,
) -> PyResult<NativeEdgeHandle> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    ensure_owner(engine.owner_id(), target.owner_id)?;
    ensure_owner(engine.owner_id(), source.owner_id)?;
    if target.state_index != state.index || source.state_index != state.index {
        return Err(crate::errors::schema_error(
            "edge handles must belong to the target assembly state",
        ));
    }
    let target_key = RecordKey {
        occurrence_index: target.occurrence_index,
        template_record_index: target.template_record_index,
    };
    {
        let state_ref = engine.state(state.index)?;
        validate_record_key(&engine, state_ref, target_key)?;
        state_ref.occurrence(source.index)?;
    }
    let owner_id = engine.owner_id();
    let state_index = state.index;
    let state_ref = engine.state_mut(state.index)?;
    let edge_index = state_ref.append_edge(target_key, source.index, operation_key, order);
    Ok(NativeEdgeHandle::new(owner_id, state_index, edge_index))
}

#[pyfunction(name = "assembly_state_mark_satisfied")]
fn assembly_state_mark_satisfied(
    mut engine: PyRefMut<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    record: PyRef<'_, NativeRecordHandle>,
) -> PyResult<()> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    ensure_owner(engine.owner_id(), record.owner_id)?;
    if record.state_index != state.index {
        return Err(crate::errors::schema_error(
            "record belongs to another native assembly state",
        ));
    }
    let record_key = RecordKey {
        occurrence_index: record.occurrence_index,
        template_record_index: record.template_record_index,
    };
    {
        let state_ref = engine.state(state.index)?;
        validate_record_key(&engine, state_ref, record_key)?;
    }
    let state_ref = engine.state_mut(state.index)?;
    state_ref.satisfied_records.insert(record_key);
    Ok(())
}

#[pyfunction(name = "assembly_state_append_overlay")]
fn assembly_state_append_overlay(
    mut engine: PyRefMut<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    target: PyRef<'_, NativeRecordHandle>,
    kind: String,
    source_label: String,
) -> PyResult<NativeOverlayHandle> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    ensure_owner(engine.owner_id(), target.owner_id)?;
    if target.state_index != state.index {
        return Err(crate::errors::schema_error(
            "overlay target belongs to another native assembly state",
        ));
    }
    let target_key = RecordKey {
        occurrence_index: target.occurrence_index,
        template_record_index: target.template_record_index,
    };
    {
        let state_ref = engine.state(state.index)?;
        validate_record_key(&engine, state_ref, target_key)?;
    }
    let owner_id = engine.owner_id();
    let state_index = state.index;
    let state_ref = engine.state_mut(state.index)?;
    let overlay_index = state_ref.append_overlay(kind, source_label, target_key);
    Ok(NativeOverlayHandle::new(
        owner_id,
        state_index,
        overlay_index,
    ))
}

#[pyfunction(name = "assembly_state_snapshot")]
fn assembly_state_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    let state_ref = engine.state(state.index)?;
    structural_snapshot(py, &engine, state_ref)
}

#[pyfunction(name = "assembly_state_index_snapshot")]
fn assembly_state_index_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    let state_ref = engine.state(state.index)?;
    index_snapshot(py, &state_ref.indexes)
}

#[pyfunction(name = "assembly_state_materialization_plan_snapshot")]
fn assembly_state_materialization_plan_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    root_occurrence_index: Option<usize>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    let state_ref = engine.state(state.index)?;
    let root = match root_occurrence_index {
        Some(index) => {
            state_ref.occurrence(index)?;
            Some(index)
        }
        None => default_root_occurrence_index(state_ref),
    };
    materialization_plan_snapshot(py, &engine, state_ref, root)
}

#[pyfunction(name = "assembly_state_query_composable_candidates")]
fn assembly_state_query_composable_candidates(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    source_template: PyRef<'_, NativeTemplateHandle>,
    request: &Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    ensure_owner(engine.owner_id(), source_template.owner_id)?;
    let surface_bundle = engine
        .surface_bundle()
        .ok_or_else(|| crate::errors::schema_error("surface bundle has not been registered"))?;
    let state_ref = engine.state(state.index)?;
    let source_template_ref = engine.template(source_template.index)?;
    let request = parse_candidate_query_request(request)?;
    let identifier_bindings =
        candidate_identifier_bindings(&engine, state_ref, &request.identifier_bindings)?;
    let target_kind_set: BTreeSet<String> =
        request.target_inventory_kinds.iter().cloned().collect();

    let mut raw_targets: Vec<RecordKey> = Vec::new();
    if request.name.is_some() && identifier_bindings.is_empty() {
        let name = request.name.as_ref().expect("checked is_some");
        if let Some(records) = state_ref.indexes.by_resource_name.get(name) {
            raw_targets.extend(records.iter().copied());
        }
    } else {
        for kind in &request.target_inventory_kinds {
            if let Some(records) = state_ref.indexes.by_inventory_kind.get(kind) {
                raw_targets.extend(records.iter().copied());
            }
        }
    }

    let candidates = PyList::empty(py);
    let mut seen_targets = BTreeSet::new();
    for target_key in raw_targets {
        if !seen_targets.insert(target_key) {
            continue;
        }
        if !record_is_visible(state_ref, target_key)? {
            continue;
        }
        let target_occurrence = state_ref.occurrence(target_key.occurrence_index)?;
        let target_template = engine.template(target_occurrence.template_index)?;
        let target_record = target_template
            .records()
            .get(target_key.template_record_index)
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native template record"))?;
        if !target_kind_set.contains(&target_record.inventory_kind) {
            continue;
        }
        let target_bindings = identifier_bindings.get(&target_key.occurrence_index);
        let target_resource_name = resolved_name(&target_record.resource_name, target_bindings);
        if let Some(name) = &request.name {
            if target_resource_name != *name {
                continue;
            }
        }
        if let Some(build_match) = &request.build_match {
            if !matches_path(build_match, &target_occurrence.build_path)? {
                continue;
            }
        }
        if let Some(owner_match) = &request.owner_match {
            let code_owner = resolved_owner(&target_record.code_owner, target_bindings);
            if !matches_path(owner_match, &code_owner)? {
                continue;
            }
        }

        let mut compatible_productions: Vec<usize> = Vec::new();
        for (production_index, production_record) in
            source_template_ref.records().iter().enumerate()
        {
            if !production_record.inventory_kind.starts_with("production.") {
                continue;
            }
            if native_production_satisfies_target(surface_bundle, target_record, production_record)
            {
                compatible_productions.push(production_index);
            }
        }
        if compatible_productions.is_empty() {
            continue;
        }

        let candidate = PyDict::new(py);
        candidate.set_item(
            "target_record",
            vec![
                target_key.occurrence_index,
                target_key.template_record_index,
            ],
        )?;
        candidate.set_item("production_records", compatible_productions)?;
        candidates.append(candidate)?;
    }

    let summary = PyDict::new(py);
    summary.set_item("candidate_count", candidates.len())?;
    let result = PyDict::new(py);
    result.set_item("candidates", candidates)?;
    result.set_item("diagnostic_summary", summary)?;
    Ok(result.into_any().unbind())
}

fn native_production_satisfies_target(
    surface_bundle: &RegisteredSurfaceBundle,
    target_record: &NativeTemplateRecord,
    production_record: &NativeTemplateRecord,
) -> bool {
    if surface_bundle
        .accepts_live_records(&target_record.surface_key, &production_record.surface_key)
    {
        return true;
    }
    target_record.surface_key == "astichi.surface.funcargs.hole"
        && matches!(
            target_record.inventory_kind.as_str(),
            "hole.positional_variadic" | "hole.named_variadic"
        )
        && production_record.surface_key == "astichi.surface.expression.production"
}

#[pyfunction(name = "assembly_state_query_demand_candidates")]
fn assembly_state_query_demand_candidates(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
    state: PyRef<'_, NativeAssemblyStateHandle>,
    request: &Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    ensure_owner(engine.owner_id(), state.owner_id)?;
    let state_ref = engine.state(state.index)?;
    let request = parse_candidate_query_request(request)?;
    let identifier_bindings =
        candidate_identifier_bindings(&engine, state_ref, &request.identifier_bindings)?;
    let target_kind_set: BTreeSet<String> =
        request.target_inventory_kinds.iter().cloned().collect();

    let mut raw_targets: Vec<RecordKey> = Vec::new();
    if request.name.is_some() && identifier_bindings.is_empty() {
        let name = request.name.as_ref().expect("checked is_some");
        if let Some(records) = state_ref.indexes.by_resource_name.get(name) {
            raw_targets.extend(records.iter().copied());
        }
    } else {
        for kind in &request.target_inventory_kinds {
            if let Some(records) = state_ref.indexes.by_inventory_kind.get(kind) {
                raw_targets.extend(records.iter().copied());
            }
        }
    }

    let candidates = PyList::empty(py);
    let mut seen_targets = BTreeSet::new();
    for target_key in raw_targets {
        if !seen_targets.insert(target_key) {
            continue;
        }
        if !record_is_visible(state_ref, target_key)? {
            continue;
        }
        let target_occurrence = state_ref.occurrence(target_key.occurrence_index)?;
        let target_template = engine.template(target_occurrence.template_index)?;
        let target_record = target_template
            .records()
            .get(target_key.template_record_index)
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native template record"))?;
        if !target_kind_set.contains(&target_record.inventory_kind) {
            continue;
        }
        let target_bindings = identifier_bindings.get(&target_key.occurrence_index);
        let target_resource_name = resolved_name(&target_record.resource_name, target_bindings);
        if let Some(name) = &request.name {
            if target_resource_name != *name {
                continue;
            }
        }
        if let Some(build_match) = &request.build_match {
            if !matches_path(build_match, &target_occurrence.build_path)? {
                continue;
            }
        }
        if let Some(owner_match) = &request.owner_match {
            let code_owner = resolved_owner(&target_record.code_owner, target_bindings);
            if !matches_path(owner_match, &code_owner)? {
                continue;
            }
        }

        let candidate = PyDict::new(py);
        candidate.set_item(
            "target_record",
            vec![
                target_key.occurrence_index,
                target_key.template_record_index,
            ],
        )?;
        candidates.append(candidate)?;
    }

    let summary = PyDict::new(py);
    summary.set_item("candidate_count", candidates.len())?;
    let result = PyDict::new(py);
    result.set_item("candidates", candidates)?;
    result.set_item("diagnostic_summary", summary)?;
    Ok(result.into_any().unbind())
}

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeTemplateHandle>()?;
    m.add_class::<NativeAssemblyStateHandle>()?;
    m.add_class::<NativeOccurrenceHandle>()?;
    m.add_class::<NativeRecordHandle>()?;
    m.add_class::<NativeEdgeHandle>()?;
    m.add_class::<NativeOverlayHandle>()?;
    m.add_function(wrap_pyfunction!(register_template_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_create, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_append_occurrence, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_record_handle, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_append_edge, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_mark_satisfied, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_append_overlay, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_index_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(
        assembly_state_materialization_plan_snapshot,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        assembly_state_query_composable_candidates,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(assembly_state_query_demand_candidates, m)?)?;
    Ok(())
}

fn parse_template_snapshot(
    snapshot: &Bound<'_, PyDict>,
    locator_base: usize,
) -> PyResult<NativeTemplate> {
    let templates = dict_items(snapshot, "templates")?;
    if templates.len() != 1 {
        return Err(crate::errors::schema_error(
            "template snapshot must contain exactly one template",
        ));
    }
    let template_meta = &templates[0];
    let locators = parse_locators(snapshot)?;
    let records = parse_records(snapshot)?;
    let record_count = get_usize(template_meta, "record_count")?;
    if record_count != records.len() {
        return Err(crate::errors::schema_error(
            "template record_count does not match records length",
        ));
    }
    Ok(NativeTemplate {
        template_key: get_string(template_meta, "template_key")?,
        source_summary: get_string(template_meta, "source_summary")?,
        locator_base,
        locators,
        records,
        package_v2: None,
        module: None,
    })
}

fn parse_locators(snapshot: &Bound<'_, PyDict>) -> PyResult<Vec<NativeLocator>> {
    let mut locators = Vec::new();
    for (index, locator) in dict_items(snapshot, "locators")?.iter().enumerate() {
        if get_usize(locator, "locator_id")? != index {
            return Err(crate::errors::schema_error(
                "template locators must be ordered by local locator_id",
            ));
        }
        locators.push(NativeLocator {
            ast_path: get_string(locator, "ast_path")?,
            authored_summary: get_string(locator, "authored_summary")?,
            materialization_anchor: get_string(locator, "materialization_anchor")?,
            parent_locator_id: get_optional_usize(locator, "parent_locator_id")?,
            role_key: get_string(locator, "role_key")?,
        });
    }
    Ok(locators)
}

fn parse_records(snapshot: &Bound<'_, PyDict>) -> PyResult<Vec<NativeTemplateRecord>> {
    let mut records = Vec::new();
    for (index, record) in dict_items(snapshot, "records")?.iter().enumerate() {
        let record_id = required(record, "record_id")?;
        let record_id = parse_usize_sequence(&record_id, "record_id")?;
        if record_id != vec![0, index] {
            return Err(crate::errors::schema_error(
                "template records must use local record ids [0, template_record_id]",
            ));
        }
        if get_usize(record, "template_record_id")? != index {
            return Err(crate::errors::schema_error(
                "template records must be ordered by template_record_id",
            ));
        }
        records.push(NativeTemplateRecord {
            code_owner: get_string_list(record, "code_owner")?,
            inventory_kind: get_string(record, "inventory_kind")?,
            locator_id: get_usize(record, "locator_id")?,
            resource_name: get_string(record, "resource_name")?,
            semantic_summary: get_string(record, "semantic_summary")?,
            surface_key: get_string(record, "surface_key")?,
        });
    }
    Ok(records)
}

fn structural_snapshot(
    py: Python<'_>,
    engine: &EngineHandle,
    state: &NativeAssemblyState,
) -> PyResult<Py<PyAny>> {
    let snapshot = PyDict::new(py);
    snapshot.set_item("schema", STRUCTURAL_SCHEMA)?;
    let surface_bundle = engine
        .surface_bundle()
        .ok_or_else(|| crate::errors::schema_error("surface bundle has not been registered"))?;
    snapshot.set_item("surface_bundle", surface_bundle.snapshot(py)?)?;
    snapshot.set_item("templates", template_list(py, engine.templates())?)?;
    snapshot.set_item("locators", locator_list(py, engine.templates())?)?;
    snapshot.set_item("occurrences", occurrence_list(py, state)?)?;
    snapshot.set_item("records", record_list(py, engine.templates(), state)?)?;
    snapshot.set_item("edges", edge_list(py, state)?)?;
    snapshot.set_item("overlays", overlay_list(py, state)?)?;
    snapshot.set_item("materialization", materialization(py)?)?;
    snapshot.set_item("diagnostics", PyList::empty(py))?;
    Ok(snapshot.into_any().unbind())
}

fn template_list(py: Python<'_>, templates: &[NativeTemplate]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (index, template) in templates.iter().enumerate() {
        let item = PyDict::new(py);
        item.set_item("record_count", template.records().len())?;
        item.set_item("source_summary", &template.source_summary)?;
        item.set_item("template_id", index)?;
        item.set_item("template_key", &template.template_key)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn locator_list(py: Python<'_>, templates: &[NativeTemplate]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (template_index, template) in templates.iter().enumerate() {
        for (local_index, locator) in template.locators().iter().enumerate() {
            let item = PyDict::new(py);
            item.set_item("ast_path", &locator.ast_path)?;
            item.set_item("authored_summary", &locator.authored_summary)?;
            item.set_item("locator_id", template.locator_base() + local_index)?;
            item.set_item("materialization_anchor", &locator.materialization_anchor)?;
            item.set_item(
                "parent_locator_id",
                locator
                    .parent_locator_id
                    .map(|parent| template.locator_base() + parent),
            )?;
            item.set_item("role_key", &locator.role_key)?;
            item.set_item("template_id", template_index)?;
            list.append(item)?;
        }
    }
    Ok(list.into_any().unbind())
}

fn occurrence_list(py: Python<'_>, state: &NativeAssemblyState) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (index, occurrence) in state.occurrences.iter().enumerate() {
        let item = PyDict::new(py);
        item.set_item("build_path", &occurrence.build_path)?;
        item.set_item("occurrence_id", index)?;
        item.set_item("parent_occurrence_id", occurrence.parent_occurrence_index)?;
        item.set_item("template_id", occurrence.template_index)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn record_list(
    py: Python<'_>,
    templates: &[NativeTemplate],
    state: &NativeAssemblyState,
) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (occurrence_index, occurrence) in state.occurrences.iter().enumerate() {
        let template = templates.get(occurrence.template_index).ok_or_else(|| {
            crate::errors::stale_handle_error("occurrence references unknown native template")
        })?;
        for (template_record_index, record) in template.records().iter().enumerate() {
            let record_key = RecordKey {
                occurrence_index,
                template_record_index,
            };
            let visible = occurrence.live && !state.dead_records.contains(&record_key);
            let satisfied = state.satisfied_records.contains(&record_key);
            let item = PyDict::new(py);
            item.set_item("code_owner", &record.code_owner)?;
            item.set_item("inventory_kind", &record.inventory_kind)?;
            item.set_item("locator_id", template.locator_base() + record.locator_id)?;
            item.set_item("occurrence_id", occurrence_index)?;
            item.set_item(
                "record_id",
                vec![
                    record_key.occurrence_index,
                    record_key.template_record_index,
                ],
            )?;
            item.set_item("resource_name", &record.resource_name)?;
            item.set_item("semantic_summary", &record.semantic_summary)?;
            let state_dict = PyDict::new(py);
            state_dict.set_item("satisfied", satisfied)?;
            state_dict.set_item("visible", visible && !satisfied)?;
            item.set_item("state", state_dict)?;
            item.set_item("surface_key", &record.surface_key)?;
            item.set_item("template_record_id", template_record_index)?;
            list.append(item)?;
        }
    }
    Ok(list.into_any().unbind())
}

fn edge_list(py: Python<'_>, state: &NativeAssemblyState) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (index, edge) in state.edges.iter().enumerate() {
        let item = PyDict::new(py);
        item.set_item("edge_id", index)?;
        item.set_item("operation_key", &edge.operation_key)?;
        item.set_item("order", edge.order)?;
        item.set_item("source_occurrence_id", edge.source_occurrence_index)?;
        item.set_item(
            "target_record_id",
            vec![
                edge.target_record.occurrence_index,
                edge.target_record.template_record_index,
            ],
        )?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn overlay_list(py: Python<'_>, state: &NativeAssemblyState) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (index, overlay) in state.overlays.iter().enumerate() {
        let item = PyDict::new(py);
        item.set_item("kind", &overlay.kind)?;
        item.set_item("overlay_id", index)?;
        item.set_item("source_label", &overlay.source_label)?;
        item.set_item(
            "target_record_id",
            vec![
                overlay.target_record.occurrence_index,
                overlay.target_record.template_record_index,
            ],
        )?;
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

fn materialization_plan_snapshot(
    py: Python<'_>,
    engine: &EngineHandle,
    state: &NativeAssemblyState,
    root_occurrence_index: Option<usize>,
) -> PyResult<Py<PyAny>> {
    validate_materialization_operation_keys(engine, state)?;
    let item = PyDict::new(py);
    item.set_item("artifact_requests", vec!["python_ast"])?;
    let debug_views = PyDict::new(py);
    debug_views.set_item("edge_count", state.edges.len())?;
    debug_views.set_item("overlay_count", state.overlays.len())?;
    let hygiene = hygiene_operation_stream(py, engine, state, root_occurrence_index)?;
    if hygiene.boundary_marker_count > 0 {
        debug_views.set_item("boundary_marker_count", hygiene.boundary_marker_count)?;
    }
    if hygiene.managed_import_request_count > 0 {
        debug_views.set_item(
            "managed_import_request_count",
            hygiene.managed_import_request_count,
        )?;
    }
    item.set_item("debug_views", debug_views)?;
    item.set_item("hygiene_stream", hygiene.stream)?;
    item.set_item(
        "operation_stream",
        materialization_operation_stream(py, state)?,
    )?;
    item.set_item("root_occurrence_id", root_occurrence_index)?;
    Ok(item.into_any().unbind())
}

fn validate_materialization_operation_keys(
    engine: &EngineHandle,
    state: &NativeAssemblyState,
) -> PyResult<()> {
    let surface_bundle = engine
        .surface_bundle()
        .ok_or_else(|| crate::errors::schema_error("surface bundle has not been registered"))?;
    let mut missing: BTreeSet<String> = BTreeSet::new();
    for edge in &state.edges {
        if !surface_bundle.has_operation_key(&edge.operation_key) {
            missing.insert(edge.operation_key.clone());
        }
    }
    for overlay in &state.overlays {
        let operation_key = overlay_operation_key(&overlay.kind);
        if !surface_bundle.has_operation_key(&operation_key) {
            missing.insert(operation_key);
        }
    }
    if !surface_bundle.has_operation_key("astichi.operation.gate_no_unresolved") {
        missing.insert("astichi.operation.gate_no_unresolved".to_string());
    }
    for operation_key in [
        "astichi.operation.keep_name",
        "astichi.operation.managed_import_request",
        "astichi.operation.rename_if_collides",
        "astichi.operation.strip_marker",
    ] {
        if !surface_bundle.has_operation_key(operation_key) {
            missing.insert(operation_key.to_string());
        }
    }
    if !missing.is_empty() {
        return Err(crate::errors::schema_error(&format!(
            "unregistered materialization operation keys: {:?}",
            missing.into_iter().collect::<Vec<_>>()
        )));
    }
    Ok(())
}

fn materialization_operation_stream(
    py: Python<'_>,
    state: &NativeAssemblyState,
) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (edge_index, edge) in state.edges.iter().enumerate() {
        let item = PyDict::new(py);
        let captures = PyDict::new(py);
        captures.set_item("edge_id", edge_index)?;
        captures.set_item("target_state", record_state(state, edge.target_record)?)?;
        item.set_item("captures", captures)?;
        item.set_item("operation_key", &edge.operation_key)?;
        item.set_item("order", edge.order)?;
        item.set_item("overlay_id", py.None())?;
        item.set_item("source_occurrence_id", edge.source_occurrence_index)?;
        item.set_item(
            "target_record_id",
            vec![
                edge.target_record.occurrence_index,
                edge.target_record.template_record_index,
            ],
        )?;
        list.append(item)?;
    }
    for (overlay_index, overlay) in state.overlays.iter().enumerate() {
        let item = PyDict::new(py);
        let captures = PyDict::new(py);
        captures.set_item("overlay_id", overlay_index)?;
        captures.set_item("overlay_kind", &overlay.kind)?;
        captures.set_item("source_label", &overlay.source_label)?;
        captures.set_item("target_state", record_state(state, overlay.target_record)?)?;
        item.set_item("captures", captures)?;
        item.set_item("operation_key", overlay_operation_key(&overlay.kind))?;
        item.set_item("order", 0)?;
        item.set_item("overlay_id", overlay_index)?;
        item.set_item("source_occurrence_id", py.None())?;
        item.set_item(
            "target_record_id",
            vec![
                overlay.target_record.occurrence_index,
                overlay.target_record.template_record_index,
            ],
        )?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

struct HygieneStreamSnapshot {
    stream: Py<PyAny>,
    boundary_marker_count: usize,
    managed_import_request_count: usize,
}

fn hygiene_operation_stream(
    py: Python<'_>,
    engine: &EngineHandle,
    state: &NativeAssemblyState,
    root_occurrence_index: Option<usize>,
) -> PyResult<HygieneStreamSnapshot> {
    let list = PyList::empty(py);
    let mut boundary_marker_count = 0;
    let managed_import_request_count =
        append_managed_import_hygiene(py, engine, state, root_occurrence_index, &list)?;
    boundary_marker_count += append_boundary_hygiene(py, engine, state, &list)?;
    boundary_marker_count += append_package_marker_hygiene(py, engine, state, &list)?;

    let item = PyDict::new(py);
    let captures = PyDict::new(py);
    captures.set_item("live_record_count", live_record_count(state)?)?;
    captures.set_item("root_occurrence_id", root_occurrence_index)?;
    captures.set_item("satisfied_record_count", state.satisfied_records.len())?;
    let (unresolved_capable, unresolved_live) = unresolved_capable_counts(engine, state)?;
    captures.set_item("unresolved_capable_record_count", unresolved_capable)?;
    captures.set_item("unresolved_live_record_count", unresolved_live)?;
    item.set_item("captures", captures)?;
    item.set_item("operation_key", "astichi.operation.gate_no_unresolved")?;
    item.set_item("record_id", py.None())?;
    item.set_item("target_scope_id", 0)?;
    list.append(item)?;
    Ok(HygieneStreamSnapshot {
        stream: list.into_any().unbind(),
        boundary_marker_count,
        managed_import_request_count,
    })
}

fn append_managed_import_hygiene(
    py: Python<'_>,
    engine: &EngineHandle,
    state: &NativeAssemblyState,
    root_occurrence_index: Option<usize>,
    list: &Bound<'_, PyList>,
) -> PyResult<usize> {
    let Some(root_occurrence_index) = root_occurrence_index else {
        return Ok(0);
    };
    let occurrence = state.occurrence(root_occurrence_index)?;
    let template = engine.template(occurrence.template_index)?;
    let Some(package) = template.package_v2() else {
        return Ok(0);
    };
    let records = package.managed_import_hygiene_specs();
    if records.is_empty() {
        return Ok(0);
    }
    let final_names = records
        .iter()
        .map(|record| record.final_local_name.clone())
        .collect::<BTreeSet<_>>();
    let collisions = final_names
        .intersection(&package.pyimport_existing_binding_names())
        .cloned()
        .collect::<Vec<_>>();
    if !collisions.is_empty() {
        let captures = PyDict::new(py);
        captures.set_item("colliding_names", collisions)?;
        captures.set_item("root_occurrence_id", root_occurrence_index)?;
        append_hygiene_item(
            py,
            list,
            "astichi.operation.rename_if_collides",
            0,
            None,
            &captures,
        )?;
    }
    for record in &records {
        let captures = PyDict::new(py);
        captures.set_item("final_local_name", &record.final_local_name)?;
        captures.set_item("module_path", record.module_path.join("."))?;
        match &record.original_symbol {
            Some(original_symbol) => captures.set_item("original_symbol", original_symbol)?,
            None => captures.set_item("original_symbol", py.None())?,
        };
        captures.set_item("root_occurrence_id", root_occurrence_index)?;
        append_hygiene_item(
            py,
            list,
            "astichi.operation.managed_import_request",
            0,
            None,
            &captures,
        )?;
    }
    Ok(records.len())
}

fn append_boundary_hygiene(
    py: Python<'_>,
    engine: &EngineHandle,
    state: &NativeAssemblyState,
    list: &Bound<'_, PyList>,
) -> PyResult<usize> {
    let mut count = 0;
    for edge in &state.edges {
        if edge.operation_key != "astichi.operation.splice_body_at_marker" {
            continue;
        }
        let source_occurrence = state.occurrence(edge.source_occurrence_index)?;
        let source_template = engine.template(source_occurrence.template_index)?;
        let Some(source_package) = source_template.package_v2() else {
            continue;
        };
        let source_scope_id = source_package.root_scope_id().unwrap_or(0);
        let source_bindings = source_package.binding_names_for_scope_id(source_scope_id);
        let target_occurrence = state.occurrence(edge.target_record.occurrence_index)?;
        let target_template = engine.template(target_occurrence.template_index)?;
        let Some(target_package) = target_template.package_v2() else {
            continue;
        };
        let locator_path = target_package
            .locator_ast_path_for_record(edge.target_record.template_record_index)
            .ok_or_else(|| crate::errors::schema_error("target record locator is missing"))?;
        let target_statement_path = block_statement_path_for_locator_path(locator_path)?;
        let boundary_names =
            target_package.boundary_available_names_for_statement_path(&target_statement_path);
        let collisions = boundary_names
            .intersection(&source_bindings)
            .cloned()
            .collect::<Vec<_>>();
        if collisions.is_empty() {
            continue;
        }
        let captures = PyDict::new(py);
        captures.set_item("colliding_names", collisions)?;
        captures.set_item("source_occurrence_id", edge.source_occurrence_index)?;
        let target_scope_id = target_package
            .scope_id_for_statement_path(&target_statement_path)
            .unwrap_or(0);
        append_hygiene_item(
            py,
            list,
            "astichi.operation.rename_if_collides",
            target_scope_id,
            Some(edge.target_record),
            &captures,
        )?;
        count += 1;
    }
    Ok(count)
}

fn append_package_marker_hygiene(
    py: Python<'_>,
    engine: &EngineHandle,
    state: &NativeAssemblyState,
    list: &Bound<'_, PyList>,
) -> PyResult<usize> {
    let mut count = 0;
    for (occurrence_index, occurrence) in state.occurrences.iter().enumerate() {
        if !occurrence.live {
            continue;
        }
        let template = engine.template(occurrence.template_index)?;
        let Some(package) = template.package_v2() else {
            continue;
        };
        for marker in package.package_marker_hygiene_specs() {
            let operation_key = if marker.source_name == "astichi_keep" {
                "astichi.operation.keep_name"
            } else {
                "astichi.operation.strip_marker"
            };
            let captures = PyDict::new(py);
            captures.set_item("marker", &marker.source_name)?;
            captures.set_item("name", &marker.resource_name)?;
            captures.set_item("occurrence_id", occurrence_index)?;
            append_hygiene_item(py, list, operation_key, marker.scope_id, None, &captures)?;
            count += 1;
        }
    }
    Ok(count)
}

fn append_hygiene_item(
    py: Python<'_>,
    list: &Bound<'_, PyList>,
    operation_key: &str,
    target_scope_id: usize,
    record_id: Option<RecordKey>,
    captures: &Bound<'_, PyDict>,
) -> PyResult<()> {
    let item = PyDict::new(py);
    item.set_item("captures", captures)?;
    item.set_item("operation_key", operation_key)?;
    match record_id {
        Some(record_id) => item.set_item(
            "record_id",
            vec![record_id.occurrence_index, record_id.template_record_index],
        )?,
        None => item.set_item("record_id", py.None())?,
    };
    item.set_item("target_scope_id", target_scope_id)?;
    list.append(item)?;
    Ok(())
}

fn unresolved_capable_counts(
    engine: &EngineHandle,
    state: &NativeAssemblyState,
) -> PyResult<(usize, usize)> {
    let mut capable = 0;
    let mut live = 0;
    for (occurrence_index, occurrence) in state.occurrences.iter().enumerate() {
        let template = engine.template(occurrence.template_index)?;
        let record_indexes = match template.package_v2() {
            Some(package) => package.unresolved_capable_record_indexes(),
            None => template
                .records()
                .iter()
                .enumerate()
                .filter_map(|(index, record)| {
                    if is_unresolved_capable_inventory_kind(&record.inventory_kind) {
                        Some(index)
                    } else {
                        None
                    }
                })
                .collect::<Vec<_>>(),
        };
        for template_record_index in record_indexes {
            capable += 1;
            let key = RecordKey {
                occurrence_index,
                template_record_index,
            };
            if record_state(state, key)? == "live" {
                live += 1;
            }
        }
    }
    Ok((capable, live))
}

fn block_statement_path_for_locator_path(path: &str) -> PyResult<String> {
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

fn is_unresolved_capable_inventory_kind(inventory_kind: &str) -> bool {
    inventory_kind.starts_with("hole.")
        || inventory_kind.ends_with(".demand")
        || inventory_kind == "external.bind"
}

fn overlay_operation_key(kind: &str) -> String {
    match kind {
        "external" => "astichi.operation.lower_external_ref".to_string(),
        "identifier" => "astichi.operation.rewrite_identifier".to_string(),
        _ => format!("astichi.operation.overlay.{kind}"),
    }
}

fn default_root_occurrence_index(state: &NativeAssemblyState) -> Option<usize> {
    state
        .occurrences
        .iter()
        .enumerate()
        .find_map(|(index, occurrence)| {
            if occurrence.parent_occurrence_index.is_none() && occurrence.live {
                Some(index)
            } else {
                None
            }
        })
}

fn live_record_count(state: &NativeAssemblyState) -> PyResult<usize> {
    let mut count = 0;
    for records in state.indexes.by_build_path.values() {
        for record_key in records {
            if record_state(state, *record_key)? == "live" {
                count += 1;
            }
        }
    }
    Ok(count)
}

fn record_state(state: &NativeAssemblyState, record_key: RecordKey) -> PyResult<&'static str> {
    let occurrence = state.occurrence(record_key.occurrence_index)?;
    if !occurrence.live || state.dead_records.contains(&record_key) {
        return Ok("dead");
    }
    if state.satisfied_records.contains(&record_key) {
        return Ok("satisfied");
    }
    Ok("live")
}

fn index_snapshot(py: Python<'_>, indexes: &NativeIndexes) -> PyResult<Py<PyAny>> {
    let snapshot = PyDict::new(py);
    snapshot.set_item(
        "by_build_path",
        vec_key_index_entries(py, &indexes.by_build_path)?,
    )?;
    snapshot.set_item(
        "by_surface",
        string_key_index_entries(py, &indexes.by_surface)?,
    )?;
    snapshot.set_item(
        "by_resource_name",
        string_key_index_entries(py, &indexes.by_resource_name)?,
    )?;
    snapshot.set_item(
        "by_inventory_kind",
        string_key_index_entries(py, &indexes.by_inventory_kind)?,
    )?;
    snapshot.set_item("by_owner", vec_key_index_entries(py, &indexes.by_owner)?)?;
    snapshot.set_item(
        "by_name_and_kind",
        name_kind_index_entries(py, &indexes.by_name_and_kind)?,
    )?;
    Ok(snapshot.into_any().unbind())
}

fn vec_key_index_entries(
    py: Python<'_>,
    map: &BTreeMap<Vec<String>, Vec<RecordKey>>,
) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (key, records) in map {
        let item = PyDict::new(py);
        item.set_item("key", key)?;
        item.set_item("records", record_key_list(py, records)?)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn string_key_index_entries(
    py: Python<'_>,
    map: &BTreeMap<String, Vec<RecordKey>>,
) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for (key, records) in map {
        let item = PyDict::new(py);
        item.set_item("key", key)?;
        item.set_item("records", record_key_list(py, records)?)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn name_kind_index_entries(
    py: Python<'_>,
    map: &BTreeMap<(String, String), Vec<RecordKey>>,
) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for ((name, kind), records) in map {
        let item = PyDict::new(py);
        item.set_item("key", vec![name, kind])?;
        item.set_item("records", record_key_list(py, records)?)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn record_key_list(py: Python<'_>, records: &[RecordKey]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for record in records {
        list.append(vec![record.occurrence_index, record.template_record_index])?;
    }
    Ok(list.into_any().unbind())
}

struct CandidateQueryRequest {
    name: Option<String>,
    build_match: Option<Vec<String>>,
    owner_match: Option<Vec<String>>,
    target_inventory_kinds: Vec<String>,
    identifier_bindings: BTreeMap<usize, BTreeMap<String, String>>,
}

fn parse_candidate_query_request(request: &Bound<'_, PyDict>) -> PyResult<CandidateQueryRequest> {
    Ok(CandidateQueryRequest {
        name: get_optional_string(request, "name")?,
        build_match: get_optional_string_list(request, "build_match")?,
        owner_match: get_optional_string_list(request, "owner_match")?,
        target_inventory_kinds: get_string_list(request, "target_inventory_kinds")?,
        identifier_bindings: get_identifier_bindings(request, "identifier_bindings")?,
    })
}

fn record_is_visible(state: &NativeAssemblyState, record_key: RecordKey) -> PyResult<bool> {
    let occurrence = state.occurrence(record_key.occurrence_index)?;
    Ok(occurrence.live
        && !state.dead_records.contains(&record_key)
        && !state.satisfied_records.contains(&record_key))
}

fn validate_record_key(
    engine: &EngineHandle,
    state: &NativeAssemblyState,
    record_key: RecordKey,
) -> PyResult<()> {
    let occurrence = state.occurrence(record_key.occurrence_index)?;
    let template = engine.template(occurrence.template_index)?;
    if record_key.template_record_index >= template.records().len() {
        return Err(crate::errors::stale_handle_error(
            "unknown native template record",
        ));
    }
    Ok(())
}

fn template_record_for_key<'a>(
    engine: &'a EngineHandle,
    state: &NativeAssemblyState,
    record_key: RecordKey,
) -> PyResult<&'a NativeTemplateRecord> {
    let template_index = state
        .occurrence(record_key.occurrence_index)?
        .template_index;
    let template = engine.template(template_index)?;
    template
        .records()
        .get(record_key.template_record_index)
        .ok_or_else(|| crate::errors::stale_handle_error("unknown native template record"))
}

fn candidate_identifier_bindings(
    engine: &EngineHandle,
    state: &NativeAssemblyState,
    request_bindings: &BTreeMap<usize, BTreeMap<String, String>>,
) -> PyResult<BTreeMap<usize, BTreeMap<String, String>>> {
    let mut bindings = BTreeMap::new();
    for overlay in &state.overlays {
        if overlay.kind != "identifier" {
            continue;
        }
        let record = template_record_for_key(engine, state, overlay.target_record)?;
        if record.resource_name.is_empty() {
            return Err(crate::errors::schema_error(
                "identifier overlay target record is missing a resource name",
            ));
        }
        bindings
            .entry(overlay.target_record.occurrence_index)
            .or_insert_with(BTreeMap::new)
            .insert(record.resource_name.clone(), overlay.source_label.clone());
    }
    for (occurrence_index, request_names) in request_bindings {
        let occurrence_bindings = bindings
            .entry(*occurrence_index)
            .or_insert_with(BTreeMap::new);
        for (source_name, target_name) in request_names {
            occurrence_bindings.insert(source_name.clone(), target_name.clone());
        }
    }
    Ok(bindings)
}

fn resolved_name(name: &str, bindings: Option<&BTreeMap<String, String>>) -> String {
    bindings
        .and_then(|items| items.get(name))
        .cloned()
        .unwrap_or_else(|| name.to_string())
}

fn resolved_owner(owner: &[String], bindings: Option<&BTreeMap<String, String>>) -> Vec<String> {
    owner
        .iter()
        .map(|part| resolved_name(part, bindings))
        .collect()
}

fn matches_path(selector: &[String], path: &[String]) -> PyResult<bool> {
    let mut memo = BTreeMap::new();
    matches_path_at(selector, path, 0, 0, &mut memo)
}

fn matches_path_at(
    selector: &[String],
    path: &[String],
    selector_index: usize,
    path_index: usize,
    memo: &mut BTreeMap<(usize, usize), bool>,
) -> PyResult<bool> {
    if let Some(value) = memo.get(&(selector_index, path_index)) {
        return Ok(*value);
    }
    let matched = if selector_index == selector.len() {
        path_index == path.len()
    } else {
        let part = &selector[selector_index];
        match part.as_str() {
            "" => {
                return Err(crate::errors::schema_error(
                    "invalid path selector: empty path selector part",
                ));
            }
            "." => {
                path_index < path.len()
                    && matches_path_at(selector, path, selector_index + 1, path_index + 1, memo)?
            }
            "?" => {
                matches_path_at(selector, path, selector_index + 1, path_index, memo)?
                    || (path_index < path.len()
                        && matches_path_at(
                            selector,
                            path,
                            selector_index + 1,
                            path_index + 1,
                            memo,
                        )?)
            }
            "*" => {
                matches_path_at(selector, path, selector_index + 1, path_index, memo)?
                    || (path_index < path.len()
                        && matches_path_at(selector, path, selector_index, path_index + 1, memo)?)
            }
            "+" => {
                path_index < path.len()
                    && (matches_path_at(selector, path, selector_index + 1, path_index + 1, memo)?
                        || matches_path_at(selector, path, selector_index, path_index + 1, memo)?)
            }
            _ => {
                if part.chars().any(|item| ".+?*/".contains(item)) {
                    return Err(crate::errors::schema_error(&format!(
                        "invalid path selector: reserved path selector character in {part:?}"
                    )));
                }
                path_index < path.len()
                    && *part == path[path_index]
                    && matches_path_at(selector, path, selector_index + 1, path_index + 1, memo)?
            }
        }
    };
    memo.insert((selector_index, path_index), matched);
    Ok(matched)
}

fn validate_snapshot_schema(snapshot: &Bound<'_, PyDict>) -> PyResult<()> {
    let schema = get_string(snapshot, "schema")?;
    if schema != STRUCTURAL_SCHEMA {
        return Err(crate::errors::schema_error(
            "unsupported template snapshot schema",
        ));
    }
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

fn dict_items<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let value = required(dict, key)?;
    let mut items = Vec::new();
    for item in value.try_iter()? {
        let item = item?;
        let item = item
            .cast::<PyDict>()
            .map_err(|_| crate::errors::schema_error(&format!("{key} entries must be dicts")))?;
        items.push(item.clone());
    }
    Ok(items)
}

fn required<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    dict.get_item(key)?
        .ok_or_else(|| crate::errors::schema_error(&format!("missing field: {key}")))
}

fn get_string(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    required(dict, key)?
        .extract::<String>()
        .map_err(|_| crate::errors::schema_error(&format!("{key} must be a string")))
}

fn get_optional_string(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    let value = required(dict, key)?;
    if value.is_none() {
        return Ok(None);
    }
    value
        .extract::<String>()
        .map(Some)
        .map_err(|_| crate::errors::schema_error(&format!("{key} must be a string or None")))
}

fn get_usize(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<usize> {
    required(dict, key)?
        .extract::<usize>()
        .map_err(|_| crate::errors::schema_error(&format!("{key} must be an unsigned integer")))
}

fn get_optional_usize(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<usize>> {
    let value = required(dict, key)?;
    if value.is_none() {
        return Ok(None);
    }
    value.extract::<usize>().map(Some).map_err(|_| {
        crate::errors::schema_error(&format!("{key} must be an unsigned integer or None"))
    })
}

fn get_string_list(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<String>> {
    let value = required(dict, key)?;
    parse_string_sequence(&value, key)
}

fn get_optional_string_list(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<Vec<String>>> {
    let value = required(dict, key)?;
    if value.is_none() {
        return Ok(None);
    }
    parse_string_sequence(&value, key).map(Some)
}

fn get_identifier_bindings(
    dict: &Bound<'_, PyDict>,
    key: &str,
) -> PyResult<BTreeMap<usize, BTreeMap<String, String>>> {
    let value = required(dict, key)?;
    if value.is_none() {
        return Ok(BTreeMap::new());
    }
    let mut bindings: BTreeMap<usize, BTreeMap<String, String>> = BTreeMap::new();
    for item in value.try_iter()? {
        let item = item?;
        let fields: Vec<Bound<'_, PyAny>> = item.try_iter()?.collect::<PyResult<Vec<_>>>()?;
        if fields.len() != 3 {
            return Err(crate::errors::schema_error(&format!(
                "{key} entries must be triples"
            )));
        }
        let occurrence_index = fields[0].extract::<usize>().map_err(|_| {
            crate::errors::schema_error(&format!(
                "{key} occurrence indexes must be unsigned integers"
            ))
        })?;
        let source_name = fields[1].extract::<String>().map_err(|_| {
            crate::errors::schema_error(&format!("{key} source names must be strings"))
        })?;
        let target_name = fields[2].extract::<String>().map_err(|_| {
            crate::errors::schema_error(&format!("{key} target names must be strings"))
        })?;
        bindings
            .entry(occurrence_index)
            .or_default()
            .insert(source_name, target_name);
    }
    Ok(bindings)
}

fn parse_string_sequence(value: &Bound<'_, PyAny>, key: &str) -> PyResult<Vec<String>> {
    let mut items = Vec::new();
    for item in value.try_iter()? {
        items.push(
            item?.extract::<String>().map_err(|_| {
                crate::errors::schema_error(&format!("{key} entries must be strings"))
            })?,
        );
    }
    Ok(items)
}

fn parse_usize_sequence(value: &Bound<'_, PyAny>, key: &str) -> PyResult<Vec<usize>> {
    let mut items = Vec::new();
    for item in value.try_iter()? {
        items.push(item?.extract::<usize>().map_err(|_| {
            crate::errors::schema_error(&format!("{key} entries must be unsigned integers"))
        })?);
    }
    Ok(items)
}

#[pymethods]
impl NativeTemplateHandle {
    #[getter]
    fn kind(&self) -> &'static str {
        HANDLE_KIND_TEMPLATE
    }

    #[getter]
    fn index(&self) -> usize {
        self.index
    }

    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        handle_snapshot(
            py,
            self.owner_id,
            HANDLE_KIND_TEMPLATE,
            self.index,
            self.generation,
        )
    }
}

#[pymethods]
impl NativeAssemblyStateHandle {
    #[getter]
    fn kind(&self) -> &'static str {
        HANDLE_KIND_ASSEMBLY_STATE
    }

    #[getter]
    fn index(&self) -> usize {
        self.index
    }

    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        handle_snapshot(
            py,
            self.owner_id,
            HANDLE_KIND_ASSEMBLY_STATE,
            self.index,
            self.generation,
        )
    }
}

#[pymethods]
impl NativeOccurrenceHandle {
    #[getter]
    fn kind(&self) -> &'static str {
        HANDLE_KIND_OCCURRENCE
    }

    #[getter]
    fn index(&self) -> usize {
        self.index
    }

    #[getter]
    fn state_index(&self) -> usize {
        self.state_index
    }

    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let snapshot = PyDict::new(py);
        snapshot.set_item("owner_id", self.owner_id)?;
        snapshot.set_item("kind", HANDLE_KIND_OCCURRENCE)?;
        snapshot.set_item("state_index", self.state_index)?;
        snapshot.set_item("index", self.index)?;
        snapshot.set_item("generation", self.generation)?;
        Ok(snapshot.into_any().unbind())
    }
}

#[pymethods]
impl NativeRecordHandle {
    #[getter]
    fn kind(&self) -> &'static str {
        HANDLE_KIND_RECORD
    }

    #[getter]
    fn occurrence_index(&self) -> usize {
        self.occurrence_index
    }

    #[getter]
    fn template_record_index(&self) -> usize {
        self.template_record_index
    }

    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let snapshot = PyDict::new(py);
        snapshot.set_item("owner_id", self.owner_id)?;
        snapshot.set_item("kind", HANDLE_KIND_RECORD)?;
        snapshot.set_item("state_index", self.state_index)?;
        snapshot.set_item("occurrence_index", self.occurrence_index)?;
        snapshot.set_item("template_record_index", self.template_record_index)?;
        snapshot.set_item("generation", self.generation)?;
        Ok(snapshot.into_any().unbind())
    }
}

#[pymethods]
impl NativeEdgeHandle {
    #[getter]
    fn kind(&self) -> &'static str {
        HANDLE_KIND_EDGE
    }

    #[getter]
    fn index(&self) -> usize {
        self.index
    }

    #[getter]
    fn state_index(&self) -> usize {
        self.state_index
    }

    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let snapshot = PyDict::new(py);
        snapshot.set_item("owner_id", self.owner_id)?;
        snapshot.set_item("kind", HANDLE_KIND_EDGE)?;
        snapshot.set_item("state_index", self.state_index)?;
        snapshot.set_item("index", self.index)?;
        snapshot.set_item("generation", self.generation)?;
        Ok(snapshot.into_any().unbind())
    }
}

#[pymethods]
impl NativeOverlayHandle {
    #[getter]
    fn kind(&self) -> &'static str {
        HANDLE_KIND_OVERLAY
    }

    #[getter]
    fn index(&self) -> usize {
        self.index
    }

    #[getter]
    fn state_index(&self) -> usize {
        self.state_index
    }

    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let snapshot = PyDict::new(py);
        snapshot.set_item("owner_id", self.owner_id)?;
        snapshot.set_item("kind", HANDLE_KIND_OVERLAY)?;
        snapshot.set_item("state_index", self.state_index)?;
        snapshot.set_item("index", self.index)?;
        snapshot.set_item("generation", self.generation)?;
        Ok(snapshot.into_any().unbind())
    }
}

fn handle_snapshot(
    py: Python<'_>,
    owner_id: u64,
    kind: &'static str,
    index: usize,
    generation: u64,
) -> PyResult<Py<PyAny>> {
    let snapshot = PyDict::new(py);
    snapshot.set_item("owner_id", owner_id)?;
    snapshot.set_item("kind", kind)?;
    snapshot.set_item("index", index)?;
    snapshot.set_item("generation", generation)?;
    Ok(snapshot.into_any().unbind())
}
