"""Experimental assembler helpers for inventory-driven builder wiring."""

from astichi.assembler.runner import AssemblyRunner
from astichi.assembler.scope import (
    AssemblyScope,
    BindingCandidate,
    BindingResource,
    ComposableCandidate,
    ComposableResource,
    DemandSelector,
    ExternalValue,
    ExternalValueCandidate,
    ExternalValueResource,
    IdentifierNameCandidate,
    IdentifierNameResource,
    as_composable,
    as_external_value,
    as_identifier,
    code_owner_parts,
    find_candidates,
    require_one,
)

__all__ = [
    "AssemblyRunner",
    "AssemblyScope",
    "BindingCandidate",
    "BindingResource",
    "ComposableCandidate",
    "ComposableResource",
    "DemandSelector",
    "ExternalValue",
    "ExternalValueCandidate",
    "ExternalValueResource",
    "IdentifierNameCandidate",
    "IdentifierNameResource",
    "as_composable",
    "as_external_value",
    "as_identifier",
    "code_owner_parts",
    "find_candidates",
    "require_one",
]
