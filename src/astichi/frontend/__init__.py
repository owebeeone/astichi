"""Source parsing and frontend entrypoints for Astichi."""

from astichi.frontend.api import compile
from astichi.frontend.compiled import CompileOrigin, FrontendComposable

__all__ = ["CompileOrigin", "FrontendComposable", "compile"]
