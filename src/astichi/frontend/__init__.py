"""Source parsing and frontend entrypoints for Astichi."""

from astichi.frontend.api import compile
from astichi.frontend.compiled import CompileOrigin, FrontendComposable
from astichi.frontend.source_kind import (
    ASTICHI_EMITTED_SOURCE,
    AUTHORED_SOURCE,
    SourceKind,
)

__all__ = [
    "ASTICHI_EMITTED_SOURCE",
    "AUTHORED_SOURCE",
    "CompileOrigin",
    "FrontendComposable",
    "SourceKind",
    "compile",
]
