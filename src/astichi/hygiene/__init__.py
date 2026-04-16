"""Lexical hygiene and name-classification support for Astichi."""

from astichi.hygiene.api import (
    HygieneResult,
    ImpliedDemand,
    NameClassification,
    analyze_names,
    rewrite_hygienically,
)

__all__ = [
    "HygieneResult",
    "ImpliedDemand",
    "NameClassification",
    "analyze_names",
    "rewrite_hygienically",
]
