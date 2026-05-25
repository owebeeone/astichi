use std::collections::{BTreeMap, BTreeSet};

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule};

use crate::handles::EngineHandle;

const STRUCTURAL_SCHEMA: &str = "astichi.structural-inventory.v1";
const HANDLE_KIND_TEMPLATE: &str = "template";
const HANDLE_KIND_ASSEMBLY_STATE: &str = "assembly-state";
const HANDLE_KIND_OCCURRENCE: &str = "occurrence";
const HANDLE_KIND_RECORD: &str = "record";

#[derive(Clone)]
pub struct NativeTemplate {
    template_key: String,
    source_summary: String,
    locator_base: usize,
    locators: Vec<NativeLocator>,
    records: Vec<NativeTemplateRecord>,
}

impl NativeTemplate {
    fn locator_base(&self) -> usize {
        self.locator_base
    }

    fn locators(&self) -> &[NativeLocator] {
        &self.locators
    }

    fn records(&self) -> &[NativeTemplateRecord] {
        &self.records
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

#[derive(Clone)]
pub struct NativeAssemblyState {
    occurrences: Vec<NativeOccurrence>,
    indexes: NativeIndexes,
    satisfied_records: BTreeSet<RecordKey>,
    dead_records: BTreeSet<RecordKey>,
}

impl NativeAssemblyState {
    pub fn new() -> Self {
        Self {
            occurrences: Vec::new(),
            indexes: NativeIndexes::default(),
            satisfied_records: BTreeSet::new(),
            dead_records: BTreeSet::new(),
        }
    }

    fn occurrence(&self, index: usize) -> PyResult<&NativeOccurrence> {
        self.occurrences
            .get(index)
            .ok_or_else(|| crate::errors::stale_handle_error("unknown native occurrence handle"))
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
}

#[derive(Clone)]
struct NativeOccurrence {
    template_index: usize,
    build_path: Vec<String>,
    parent_occurrence_index: Option<usize>,
    live: bool,
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
struct RecordKey {
    occurrence_index: usize,
    template_record_index: usize,
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

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeTemplateHandle>()?;
    m.add_class::<NativeAssemblyStateHandle>()?;
    m.add_class::<NativeOccurrenceHandle>()?;
    m.add_class::<NativeRecordHandle>()?;
    m.add_function(wrap_pyfunction!(register_template_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_create, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_append_occurrence, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_record_handle, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(assembly_state_index_snapshot, m)?)?;
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
    snapshot.set_item("edges", PyList::empty(py))?;
    snapshot.set_item("overlays", PyList::empty(py))?;
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

fn materialization(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let item = PyDict::new(py);
    item.set_item("artifact_requests", PyList::empty(py))?;
    item.set_item("debug_views", PyDict::new(py))?;
    item.set_item("hygiene_stream", PyList::empty(py))?;
    item.set_item("operation_stream", PyList::empty(py))?;
    item.set_item("root_occurrence_id", py.None())?;
    Ok(item.into_any().unbind())
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
