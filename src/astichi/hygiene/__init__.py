"""Lexical hygiene and name-classification support for Astichi."""

from astichi.hygiene.api import (
    HygieneResult,
    ImpliedDemand,
    LexicalOccurrence,
    NameClassification,
    ScopeAnalysis,
    ScopeId,
    analyze_names,
    assign_scope_identity,
    rename_scope_collisions,
    rewrite_hygienically,
)

__all__ = [
    "HygieneResult",
    "ImpliedDemand",
    "LexicalOccurrence",
    "NameClassification",
    "ScopeAnalysis",
    "ScopeId",
    "analyze_names",
    "assign_scope_identity",
    "rename_scope_collisions",
    "rewrite_hygienically",
]
