use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyModule};

use crate::handles::EngineHandle;

const STRUCTURAL_SCHEMA: &str = "astichi.structural-inventory.v1";

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
    reject_marker_bearing_source(&source)?;

    let filename = filename.unwrap_or_else(|| "<astichi-native>".to_string());
    let module = crate::parser_ir::parse_native_module(&source, &filename)?;
    let source_summary = "compile line=".to_string() + &line_number.to_string() + " records=1";
    let ast_dump = crate::parser_ir::ast_dump_without_attributes(py, &source, &module)?;
    let template_key = template_key(py, &ast_dump, &source_summary)?;

    structural_snapshot(
        py,
        surface_bundle.snapshot(py)?,
        &template_key,
        &source_summary,
        line_number,
    )
}

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_template_snapshot, m)?)?;
    Ok(())
}

fn reject_marker_bearing_source(source: &str) -> PyResult<()> {
    if source.contains("astichi_") || source.contains("__astichi_") {
        return Err(crate::errors::schema_error(
            "native N4a template extraction only supports marker-free source",
        ));
    }
    Ok(())
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
    line_number: u32,
) -> PyResult<Py<PyAny>> {
    let snapshot = PyDict::new(py);
    snapshot.set_item("schema", STRUCTURAL_SCHEMA)?;
    snapshot.set_item("surface_bundle", surface_bundle)?;
    snapshot.set_item("templates", templates(py, template_key, source_summary)?)?;
    snapshot.set_item("locators", locators(py, line_number)?)?;
    snapshot.set_item("occurrences", occurrences(py)?)?;
    snapshot.set_item("records", records(py)?)?;
    snapshot.set_item("edges", PyList::empty(py))?;
    snapshot.set_item("overlays", PyList::empty(py))?;
    snapshot.set_item("materialization", materialization(py)?)?;
    snapshot.set_item("diagnostics", PyList::empty(py))?;
    Ok(snapshot.into_any().unbind())
}

fn templates(py: Python<'_>, template_key: &str, source_summary: &str) -> PyResult<Py<PyAny>> {
    let item = PyDict::new(py);
    item.set_item("record_count", 1)?;
    item.set_item("source_summary", source_summary)?;
    item.set_item("template_id", 0)?;
    item.set_item("template_key", template_key)?;
    let list = PyList::empty(py);
    list.append(item)?;
    Ok(list.into_any().unbind())
}

fn locators(py: Python<'_>, line_number: u32) -> PyResult<Py<PyAny>> {
    let item = PyDict::new(py);
    item.set_item("ast_path", ".")?;
    item.set_item(
        "authored_summary",
        "__block__ at line ".to_string() + &line_number.to_string(),
    )?;
    item.set_item("locator_id", 0)?;
    item.set_item("materialization_anchor", "copy-block")?;
    item.set_item("parent_locator_id", py.None())?;
    item.set_item("role_key", "production.block")?;
    item.set_item("template_id", 0)?;
    let list = PyList::empty(py);
    list.append(item)?;
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

fn records(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let item = PyDict::new(py);
    item.set_item("code_owner", Vec::<&str>::new())?;
    item.set_item("inventory_kind", "production.block")?;
    item.set_item("locator_id", 0)?;
    item.set_item("occurrence_id", 0)?;
    item.set_item("record_id", vec![0, 0])?;
    item.set_item("resource_name", "__block__")?;
    item.set_item(
        "semantic_summary",
        "production.block name=__block__ owner=. build_path=.",
    )?;
    let state = PyDict::new(py);
    state.set_item("satisfied", false)?;
    state.set_item("visible", true)?;
    item.set_item("state", state)?;
    item.set_item("surface_key", "astichi.surface.block.production")?;
    item.set_item("template_record_id", 0)?;
    let list = PyList::empty(py);
    list.append(item)?;
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
