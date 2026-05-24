use std::collections::HashSet;

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule};

use crate::handles::EngineHandle;

const SURFACE_BUNDLE_SCHEMA_VERSION: u32 = 1;

#[derive(Clone)]
pub struct RegisteredSurfaceBundle {
    bundle_key: String,
    schema_version: u32,
    bundle_signature: String,
    surfaces: Vec<SurfaceSpec>,
    operations: Vec<OperationSpec>,
    patterns: Vec<PatternSpec>,
    compatibility_rules: Vec<CompatibilityRule>,
}

impl RegisteredSurfaceBundle {
    pub fn from_snapshot(snapshot: &Bound<'_, PyDict>) -> PyResult<Self> {
        let schema_version = get_u32(snapshot, "schema_version")?;
        if schema_version != SURFACE_BUNDLE_SCHEMA_VERSION {
            return Err(crate::errors::schema_error(
                "unsupported surface bundle schema",
            ));
        }

        let surfaces = parse_surface_specs(snapshot)?;
        let operations = parse_operation_specs(snapshot)?;
        let patterns = parse_pattern_specs(snapshot)?;
        let compatibility_rules = parse_compatibility_rules(snapshot)?;

        reject_duplicate_keys(
            surfaces.iter().map(|item| item.surface_key.as_str()),
            "surface",
        )?;
        reject_duplicate_keys(
            operations.iter().map(|item| item.operation_key.as_str()),
            "operation",
        )?;
        reject_duplicate_keys(
            patterns.iter().map(|item| item.pattern_key.as_str()),
            "pattern",
        )?;

        let surface_keys: HashSet<&str> = surfaces
            .iter()
            .map(|surface| surface.surface_key.as_str())
            .collect();
        let operation_keys: HashSet<&str> = operations
            .iter()
            .map(|operation| operation.operation_key.as_str())
            .collect();
        for pattern in &patterns {
            if !surface_keys.contains(pattern.surface_key.as_str()) {
                return Err(crate::errors::schema_error(&format!(
                    "pattern references unknown surface: {}",
                    pattern.surface_key
                )));
            }
            if !operation_keys.contains(pattern.operation_key.as_str()) {
                return Err(crate::errors::schema_error(&format!(
                    "pattern references unknown operation: {}",
                    pattern.operation_key
                )));
            }
        }
        for rule in &compatibility_rules {
            if !surface_keys.contains(rule.target_surface_key.as_str()) {
                return Err(crate::errors::schema_error(&format!(
                    "rule references unknown target surface: {}",
                    rule.target_surface_key
                )));
            }
            if !surface_keys.contains(rule.production_surface_key.as_str()) {
                return Err(crate::errors::schema_error(&format!(
                    "rule references unknown production surface: {}",
                    rule.production_surface_key
                )));
            }
        }

        Ok(Self {
            bundle_key: get_string(snapshot, "bundle_key")?,
            schema_version,
            bundle_signature: get_string(snapshot, "bundle_signature")?,
            surfaces,
            operations,
            patterns,
            compatibility_rules,
        })
    }

    pub fn surface_count(&self) -> usize {
        self.surfaces.len()
    }

    pub fn operation_count(&self) -> usize {
        self.operations.len()
    }

    pub fn pattern_count(&self) -> usize {
        self.patterns.len()
    }

    pub fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        dict.set_item("bundle_key", &self.bundle_key)?;
        dict.set_item("bundle_signature", &self.bundle_signature)?;
        dict.set_item(
            "compatibility_rules",
            compatibility_rule_list(py, &self.compatibility_rules)?,
        )?;
        dict.set_item("operations", operation_list(py, &self.operations)?)?;
        dict.set_item("patterns", pattern_list(py, &self.patterns)?)?;
        dict.set_item("schema_version", self.schema_version)?;
        dict.set_item("surfaces", surface_list(py, &self.surfaces)?)?;
        Ok(dict.into_any().unbind())
    }
}

#[derive(Clone)]
struct SurfaceSpec {
    surface_key: String,
    version: u32,
    summary: String,
    _handle_index: usize,
}

#[derive(Clone)]
struct OperationSpec {
    operation_key: String,
    version: u32,
    summary: String,
    _handle_index: usize,
}

#[derive(Clone)]
struct PatternSpec {
    pattern_key: String,
    template_key: String,
    version: u32,
    surface_key: String,
    operation_key: String,
    summary: String,
    enabled: bool,
    diagnostic_only: bool,
    _matcher_kind: String,
    _handle_index: usize,
}

#[derive(Clone)]
struct CompatibilityRule {
    target_surface_key: String,
    production_surface_key: String,
    predicate: ShapePredicate,
    result_policy: ResultPolicy,
}

#[derive(Clone)]
struct ShapePredicate {
    target_expectations: Vec<FieldExpectation>,
    production_expectations: Vec<FieldExpectation>,
}

#[derive(Clone)]
struct FieldExpectation {
    field_name: String,
    expected_value: String,
}

#[derive(Clone)]
struct ResultPolicy {
    policy_key: String,
    summary: String,
}

#[pyfunction]
pub fn register_surface_bundle(
    py: Python<'_>,
    mut engine: PyRefMut<'_, EngineHandle>,
    bundle: &Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    let registered = RegisteredSurfaceBundle::from_snapshot(bundle)?;
    let snapshot = registered.snapshot(py)?;
    engine.set_surface_bundle(registered)?;
    Ok(snapshot)
}

#[pyfunction]
pub fn surface_bundle_snapshot(
    py: Python<'_>,
    engine: PyRef<'_, EngineHandle>,
) -> PyResult<Py<PyAny>> {
    engine.ensure_open()?;
    match engine.surface_bundle() {
        Some(bundle) => bundle.snapshot(py),
        None => Err(crate::errors::schema_error(
            "surface bundle has not been registered",
        )),
    }
}

pub fn register_module_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(register_surface_bundle, m)?)?;
    m.add_function(wrap_pyfunction!(surface_bundle_snapshot, m)?)?;
    Ok(())
}

fn parse_surface_specs(snapshot: &Bound<'_, PyDict>) -> PyResult<Vec<SurfaceSpec>> {
    parse_list(snapshot, "surfaces", |index, item| {
        Ok(SurfaceSpec {
            surface_key: get_string(item, "surface_key")?,
            version: get_u32(item, "version")?,
            summary: get_string(item, "summary")?,
            _handle_index: index,
        })
    })
}

fn parse_operation_specs(snapshot: &Bound<'_, PyDict>) -> PyResult<Vec<OperationSpec>> {
    parse_list(snapshot, "operations", |index, item| {
        Ok(OperationSpec {
            operation_key: get_string(item, "operation_key")?,
            version: get_u32(item, "version")?,
            summary: get_string(item, "summary")?,
            _handle_index: index,
        })
    })
}

fn parse_pattern_specs(snapshot: &Bound<'_, PyDict>) -> PyResult<Vec<PatternSpec>> {
    parse_list(snapshot, "patterns", |index, item| {
        let template_key = get_string(item, "template_key")?;
        Ok(PatternSpec {
            pattern_key: get_string(item, "pattern_key")?,
            template_key: template_key.clone(),
            version: get_u32(item, "version")?,
            surface_key: get_string(item, "surface_key")?,
            operation_key: get_string(item, "operation_key")?,
            summary: get_string(item, "summary")?,
            enabled: get_bool(item, "enabled")?,
            diagnostic_only: get_bool(item, "diagnostic_only")?,
            _matcher_kind: matcher_kind(&template_key)?,
            _handle_index: index,
        })
    })
}

fn parse_compatibility_rules(snapshot: &Bound<'_, PyDict>) -> PyResult<Vec<CompatibilityRule>> {
    parse_list(snapshot, "compatibility_rules", |_index, item| {
        let predicate = get_dict(item, "predicate")?;
        let result_policy = get_dict(item, "result_policy")?;
        Ok(CompatibilityRule {
            target_surface_key: get_string(item, "target_surface_key")?,
            production_surface_key: get_string(item, "production_surface_key")?,
            predicate: ShapePredicate {
                target_expectations: parse_field_expectations(&predicate, "target_expectations")?,
                production_expectations: parse_field_expectations(
                    &predicate,
                    "production_expectations",
                )?,
            },
            result_policy: ResultPolicy {
                policy_key: get_string(&result_policy, "policy_key")?,
                summary: get_string(&result_policy, "summary")?,
            },
        })
    })
}

fn parse_field_expectations(
    predicate: &Bound<'_, PyDict>,
    key: &str,
) -> PyResult<Vec<FieldExpectation>> {
    parse_list(predicate, key, |_index, item| {
        Ok(FieldExpectation {
            field_name: get_string(item, "field_name")?,
            expected_value: get_string(item, "expected_value")?,
        })
    })
}

fn parse_list<T>(
    dict: &Bound<'_, PyDict>,
    key: &str,
    mut parse_item: impl FnMut(usize, &Bound<'_, PyDict>) -> PyResult<T>,
) -> PyResult<Vec<T>> {
    let value = required(dict, key)?;
    let mut parsed = Vec::new();
    for (index, item) in value.try_iter()?.enumerate() {
        let item = item?;
        let item = item
            .cast::<PyDict>()
            .map_err(|_| crate::errors::schema_error(&format!("{key} entries must be dicts")))?;
        parsed.push(parse_item(index, item)?);
    }
    Ok(parsed)
}

fn required<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    dict.get_item(key)?
        .ok_or_else(|| crate::errors::schema_error(&format!("missing field: {key}")))
}

fn get_dict<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyDict>> {
    let value = required(dict, key)?;
    Ok(value
        .cast::<PyDict>()
        .map_err(|_| crate::errors::schema_error(&format!("{key} must be a dict")))?
        .clone())
}

fn get_string(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    required(dict, key)?
        .extract::<String>()
        .map_err(|_| crate::errors::schema_error(&format!("{key} must be a string")))
}

fn get_u32(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<u32> {
    required(dict, key)?
        .extract::<u32>()
        .map_err(|_| crate::errors::schema_error(&format!("{key} must be an unsigned integer")))
}

fn get_bool(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<bool> {
    required(dict, key)?
        .extract::<bool>()
        .map_err(|_| crate::errors::schema_error(&format!("{key} must be a bool")))
}

fn matcher_kind(template_key: &str) -> PyResult<String> {
    if template_key.is_empty() {
        return Err(crate::errors::schema_error(
            "pattern template_key must not be empty",
        ));
    }
    Ok(template_key
        .split('+')
        .next()
        .unwrap_or(template_key)
        .to_string())
}

fn reject_duplicate_keys<'a>(keys: impl Iterator<Item = &'a str>, label: &str) -> PyResult<()> {
    let mut seen = HashSet::new();
    let mut duplicates = Vec::new();
    for key in keys {
        if !seen.insert(key) && !duplicates.contains(&key) {
            duplicates.push(key);
        }
    }
    if duplicates.is_empty() {
        return Ok(());
    }
    Err(crate::errors::schema_error(&format!(
        "duplicate {label} keys: {duplicates:?}"
    )))
}

fn surface_list(py: Python<'_>, surfaces: &[SurfaceSpec]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for surface in surfaces {
        let item = PyDict::new(py);
        item.set_item("summary", &surface.summary)?;
        item.set_item("surface_key", &surface.surface_key)?;
        item.set_item("version", surface.version)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn operation_list(py: Python<'_>, operations: &[OperationSpec]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for operation in operations {
        let item = PyDict::new(py);
        item.set_item("operation_key", &operation.operation_key)?;
        item.set_item("summary", &operation.summary)?;
        item.set_item("version", operation.version)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn pattern_list(py: Python<'_>, patterns: &[PatternSpec]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for pattern in patterns {
        let item = PyDict::new(py);
        item.set_item("diagnostic_only", pattern.diagnostic_only)?;
        item.set_item("enabled", pattern.enabled)?;
        item.set_item("operation_key", &pattern.operation_key)?;
        item.set_item("pattern_key", &pattern.pattern_key)?;
        item.set_item("summary", &pattern.summary)?;
        item.set_item("surface_key", &pattern.surface_key)?;
        item.set_item("template_key", &pattern.template_key)?;
        item.set_item("version", pattern.version)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn compatibility_rule_list(py: Python<'_>, rules: &[CompatibilityRule]) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for rule in rules {
        let item = PyDict::new(py);
        item.set_item("predicate", predicate_snapshot(py, &rule.predicate)?)?;
        item.set_item("production_surface_key", &rule.production_surface_key)?;
        item.set_item(
            "result_policy",
            result_policy_snapshot(py, &rule.result_policy)?,
        )?;
        item.set_item("target_surface_key", &rule.target_surface_key)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn predicate_snapshot(py: Python<'_>, predicate: &ShapePredicate) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item(
        "production_expectations",
        field_expectation_list(py, &predicate.production_expectations)?,
    )?;
    dict.set_item(
        "target_expectations",
        field_expectation_list(py, &predicate.target_expectations)?,
    )?;
    Ok(dict.into_any().unbind())
}

fn field_expectation_list(
    py: Python<'_>,
    expectations: &[FieldExpectation],
) -> PyResult<Py<PyAny>> {
    let list = PyList::empty(py);
    for expectation in expectations {
        let item = PyDict::new(py);
        item.set_item("expected_value", &expectation.expected_value)?;
        item.set_item("field_name", &expectation.field_name)?;
        list.append(item)?;
    }
    Ok(list.into_any().unbind())
}

fn result_policy_snapshot(py: Python<'_>, policy: &ResultPolicy) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("policy_key", &policy.policy_key)?;
    dict.set_item("summary", &policy.summary)?;
    Ok(dict.into_any().unbind())
}
