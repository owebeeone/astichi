"""astichi — AST composition for ahead-of-time Python codegen."""

__version__ = "1.0.7"

from astichi.builder import build
from astichi.cache import GeneratedAstCache
from astichi.frontend import compile
from astichi.model import Composable, ComposableDescription, ComposableHole, TargetAddress

__all__ = [
    "__version__",
    "Composable",
    "ComposableDescription",
    "ComposableHole",
    "GeneratedAstCache",
    "TargetAddress",
    "build",
    "compile",
]
