"""Surface bundle registration for the lower engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any

from astichi.lower_engine.errors import LowerEngineError, StaleHandleError
from astichi.lower_engine.handles import (
    EngineOwner,
    OperationId,
    PatternId,
    SurfaceId,
)
from astichi.structural_snapshot import SCHEMA

SURFACE_BUNDLE_SCHEMA_VERSION = 1


class BundleSchemaMismatchError(LowerEngineError):
    """Raised when a serialized surface bundle cannot be registered."""


@dataclass(frozen=True, slots=True)
class SurfaceSpec:
    surface_key: str
    version: int
    summary: str
    handle: SurfaceId | None = None


@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation_key: str
    version: int
    summary: str
    handle: OperationId | None = None


@dataclass(frozen=True, slots=True)
class PatternSpec:
    pattern_key: str
    template_key: str
    version: int
    surface_key: str
    operation_key: str
    summary: str
    enabled: bool = True
    diagnostic_only: bool = False
    handle: PatternId | None = None


@dataclass(frozen=True, slots=True)
class ShapeFieldExpectation:
    field_name: str
    expected_value: str

    def matches(self, shape: Mapping[str, str]) -> bool:
        """Return whether one structural shape has the expected field value."""
        return shape.get(self.field_name) == self.expected_value


@dataclass(frozen=True, slots=True)
class ShapePredicateDescriptor:
    target_expectations: tuple[ShapeFieldExpectation, ...] = ()
    production_expectations: tuple[ShapeFieldExpectation, ...] = ()

    def matches(
        self,
        *,
        target_shape: Mapping[str, str],
        production_shape: Mapping[str, str],
    ) -> bool:
        """Evaluate a callback-free structural compatibility predicate."""
        return all(
            expectation.matches(target_shape)
            for expectation in self.target_expectations
        ) and all(
            expectation.matches(production_shape)
            for expectation in self.production_expectations
        )

    def snapshot(self) -> dict[str, Any]:
        """Return the canonical JSON shape for this descriptor."""
        return {
            "production_expectations": [
                _field_expectation_snapshot(expectation)
                for expectation in self.production_expectations
            ],
            "target_expectations": [
                _field_expectation_snapshot(expectation)
                for expectation in self.target_expectations
            ],
        }


@dataclass(frozen=True, slots=True)
class ResultPolicyDescriptor:
    policy_key: str
    summary: str

    def snapshot(self) -> dict[str, str]:
        """Return the canonical JSON shape for this policy."""
        return {
            "policy_key": self.policy_key,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class CompatibilityRuleSpec:
    target_surface_key: str
    production_surface_key: str
    shape_predicate: ShapePredicateDescriptor
    result_policy: ResultPolicyDescriptor


@dataclass(frozen=True, slots=True)
class CompatibilityDecision:
    accepted: bool
    result_policy: ResultPolicyDescriptor | None = None


@dataclass(frozen=True, slots=True)
class SurfaceBundleSpec:
    bundle_key: str
    schema_version: int
    surfaces: tuple[SurfaceSpec, ...]
    operations: tuple[OperationSpec, ...]
    patterns: tuple[PatternSpec, ...]
    compatibility_rules: tuple[CompatibilityRuleSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class RegisteredSurfaceBundle:
    bundle_key: str
    schema_version: int
    bundle_signature: str
    surfaces: tuple[SurfaceSpec, ...]
    operations: tuple[OperationSpec, ...]
    patterns: tuple[PatternSpec, ...]
    compatibility_rules: tuple[CompatibilityRuleSpec, ...]

    def snapshot(self) -> dict[str, Any]:
        """Return the structural snapshot surface bundle section."""
        return {
            "bundle_key": self.bundle_key,
            "bundle_signature": self.bundle_signature,
            "compatibility_rules": [
                _compatibility_rule_snapshot(rule)
                for rule in self.compatibility_rules
            ],
            "operations": [
                {
                    "operation_key": operation.operation_key,
                    "summary": operation.summary,
                    "version": operation.version,
                }
                for operation in self.operations
            ],
            "patterns": [
                {
                    "diagnostic_only": pattern.diagnostic_only,
                    "enabled": pattern.enabled,
                    "operation_key": pattern.operation_key,
                    "pattern_key": pattern.pattern_key,
                    "summary": pattern.summary,
                    "surface_key": pattern.surface_key,
                    "template_key": pattern.template_key,
                    "version": pattern.version,
                }
                for pattern in self.patterns
            ],
            "schema_version": self.schema_version,
            "surfaces": [
                {
                    "summary": surface.summary,
                    "surface_key": surface.surface_key,
                    "version": surface.version,
                }
                for surface in self.surfaces
            ],
        }


class SurfaceRegistry:
    """Register one lower-engine surface bundle and validate its handles."""

    def __init__(self, owner: EngineOwner) -> None:
        self._owner = owner
        self._bundle: RegisteredSurfaceBundle | None = None
        self._surfaces_by_key: dict[str, SurfaceSpec] = {}
        self._operations_by_key: dict[str, OperationSpec] = {}
        self._patterns_by_key: dict[str, PatternSpec] = {}

    @property
    def bundle(self) -> RegisteredSurfaceBundle | None:
        """Return the registered bundle, if one has been loaded."""
        return self._bundle

    def register_bundle(self, spec: SurfaceBundleSpec) -> RegisteredSurfaceBundle:
        """Register a canonical bundle and bind dynamic handles to its specs."""
        if spec.schema_version != SURFACE_BUNDLE_SCHEMA_VERSION:
            raise BundleSchemaMismatchError(
                f"unsupported surface bundle schema: {spec.schema_version}"
            )
        if self._bundle is not None:
            raise LowerEngineError("surface bundle is already registered")
        _reject_duplicate_keys(
            [surface.surface_key for surface in spec.surfaces],
            "surface",
        )
        _reject_duplicate_keys(
            [operation.operation_key for operation in spec.operations],
            "operation",
        )
        _reject_duplicate_keys(
            [pattern.pattern_key for pattern in spec.patterns],
            "pattern",
        )

        surface_keys = {surface.surface_key for surface in spec.surfaces}
        operation_keys = {operation.operation_key for operation in spec.operations}
        for pattern in spec.patterns:
            if pattern.surface_key not in surface_keys:
                raise LowerEngineError(
                    f"pattern references unknown surface: {pattern.surface_key}"
                )
            if pattern.operation_key not in operation_keys:
                raise LowerEngineError(
                    f"pattern references unknown operation: {pattern.operation_key}"
                )
        for rule in spec.compatibility_rules:
            if rule.target_surface_key not in surface_keys:
                raise LowerEngineError(
                    f"rule references unknown target surface: {rule.target_surface_key}"
                )
            if rule.production_surface_key not in surface_keys:
                raise LowerEngineError(
                    "rule references unknown production surface: "
                    f"{rule.production_surface_key}"
                )

        surfaces = tuple(
            replace(surface, handle=SurfaceId(owner=self._owner, index=index))
            for index, surface in enumerate(spec.surfaces)
        )
        operations = tuple(
            replace(operation, handle=OperationId(owner=self._owner, index=index))
            for index, operation in enumerate(spec.operations)
        )
        patterns = tuple(
            replace(pattern, handle=PatternId(owner=self._owner, index=index))
            for index, pattern in enumerate(spec.patterns)
        )
        registered = RegisteredSurfaceBundle(
            bundle_key=spec.bundle_key,
            schema_version=spec.schema_version,
            bundle_signature=_bundle_signature(
                SurfaceBundleSpec(
                    bundle_key=spec.bundle_key,
                    schema_version=spec.schema_version,
                    surfaces=surfaces,
                    operations=operations,
                    patterns=patterns,
                    compatibility_rules=spec.compatibility_rules,
                )
            ),
            surfaces=surfaces,
            operations=operations,
            patterns=patterns,
            compatibility_rules=spec.compatibility_rules,
        )
        self._bundle = registered
        self._surfaces_by_key = {surface.surface_key: surface for surface in surfaces}
        self._operations_by_key = {
            operation.operation_key: operation for operation in operations
        }
        self._patterns_by_key = {pattern.pattern_key: pattern for pattern in patterns}
        return registered

    def surface_handle(self, surface_key: str) -> SurfaceId:
        """Return the dynamic handle for a registered surface key."""
        self._require_bundle()
        handle = self._surfaces_by_key[surface_key].handle
        assert handle is not None
        return handle

    def operation_handle(self, operation_key: str) -> OperationId:
        """Return the dynamic handle for a registered operation key."""
        self._require_bundle()
        handle = self._operations_by_key[operation_key].handle
        assert handle is not None
        return handle

    def pattern_handle(self, pattern_key: str) -> PatternId:
        """Return the dynamic handle for a registered pattern key."""
        self._require_bundle()
        handle = self._patterns_by_key[pattern_key].handle
        assert handle is not None
        return handle

    def compatibility_decision(
        self,
        *,
        target_surface_id: SurfaceId,
        production_surface_id: SurfaceId,
        target_shape: Mapping[str, str],
        production_shape: Mapping[str, str],
    ) -> CompatibilityDecision:
        """Evaluate compatibility using registered structural descriptors."""
        self._require_bundle()
        target = self._surface_by_handle(target_surface_id)
        production = self._surface_by_handle(production_surface_id)
        assert self._bundle is not None
        for rule in self._bundle.compatibility_rules:
            if (
                rule.target_surface_key == target.surface_key
                and rule.production_surface_key == production.surface_key
                and rule.shape_predicate.matches(
                    target_shape=target_shape,
                    production_shape=production_shape,
                )
            ):
                return CompatibilityDecision(
                    accepted=True,
                    result_policy=rule.result_policy,
                )
        return CompatibilityDecision(accepted=False)

    def structural_snapshot(self) -> dict[str, Any]:
        """Render the registered surface bundle as an otherwise empty snapshot."""
        bundle = self._require_bundle()
        return {
            "schema": SCHEMA,
            "surface_bundle": bundle.snapshot(),
            "templates": [],
            "locators": [],
            "occurrences": [],
            "records": [],
            "edges": [],
            "overlays": [],
            "materialization": {
                "artifact_requests": [],
                "debug_views": {},
                "hygiene_stream": [],
                "operation_stream": [],
                "root_occurrence_id": None,
            },
            "diagnostics": [],
        }

    def _surface_by_handle(self, handle: SurfaceId) -> SurfaceSpec:
        if handle.owner != self._owner:
            raise StaleHandleError("surface handle belongs to another lower engine")
        assert self._bundle is not None
        try:
            return self._bundle.surfaces[handle.index]
        except IndexError as exc:
            raise StaleHandleError(f"unknown surface handle: {handle.index}") from exc

    def _require_bundle(self) -> RegisteredSurfaceBundle:
        if self._bundle is None:
            raise LowerEngineError("surface bundle has not been registered")
        return self._bundle


def _bundle_signature(spec: SurfaceBundleSpec) -> str:
    payload = {
        "bundle_key": spec.bundle_key,
        "compatibility_rules": [
            _compatibility_rule_snapshot(rule)
            for rule in spec.compatibility_rules
        ],
        "operations": [
            {
                "operation_key": operation.operation_key,
                "summary": operation.summary,
                "version": operation.version,
            }
            for operation in spec.operations
        ],
        "patterns": [
            {
                "diagnostic_only": pattern.diagnostic_only,
                "enabled": pattern.enabled,
                "operation_key": pattern.operation_key,
                "pattern_key": pattern.pattern_key,
                "summary": pattern.summary,
                "surface_key": pattern.surface_key,
                "template_key": pattern.template_key,
                "version": pattern.version,
            }
            for pattern in spec.patterns
        ],
        "schema_version": spec.schema_version,
        "surfaces": [
            {
                "summary": surface.summary,
                "surface_key": surface.surface_key,
                "version": surface.version,
            }
            for surface in spec.surfaces
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _compatibility_rule_snapshot(rule: CompatibilityRuleSpec) -> dict[str, Any]:
    return {
        "predicate": rule.shape_predicate.snapshot(),
        "production_surface_key": rule.production_surface_key,
        "result_policy": rule.result_policy.snapshot(),
        "target_surface_key": rule.target_surface_key,
    }


def _field_expectation_snapshot(expectation: ShapeFieldExpectation) -> dict[str, str]:
    return {
        "expected_value": expectation.expected_value,
        "field_name": expectation.field_name,
    }


def _reject_duplicate_keys(keys: list[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for key in keys:
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        raise LowerEngineError(f"duplicate {label} keys: {duplicates}")
