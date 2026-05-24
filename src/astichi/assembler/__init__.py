"""Experimental assembler helpers for inventory-driven builder wiring."""

from astichi.assembler.client import BuildIndex
from astichi.assembler.runner import AssemblyRunner
from astichi.assembler.production import (
    BindingSpec,
    BuildProductionSpec,
    ProductionCatalog,
    ProductionRequest,
    ProductionSpec,
    ProductionTemplateProvider,
    ProductionValueProvider,
    SourceProvider,
    TargetSpec,
    TemplateChoice,
    TemplateProducerSpec,
    build_production_roots,
)
from astichi.assembler.scope import (
    AssemblyScope,
    as_composable,
    as_external_value,
    as_identifier,
    find_candidates,
    require_one,
)

__all__ = [
    "AssemblyRunner",
    "AssemblyScope",
    "BindingSpec",
    "BuildIndex",
    "BuildProductionSpec",
    "ProductionCatalog",
    "ProductionRequest",
    "ProductionSpec",
    "ProductionTemplateProvider",
    "ProductionValueProvider",
    "SourceProvider",
    "TargetSpec",
    "TemplateChoice",
    "TemplateProducerSpec",
    "as_composable",
    "as_external_value",
    "as_identifier",
    "build_production_roots",
    "find_candidates",
    "require_one",
]
