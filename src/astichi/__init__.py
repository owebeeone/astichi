"""astichi — AST composition for ahead-of-time Python codegen."""

__version__ = "0.1.0"

from astichi.builder import build
from astichi.frontend import compile
from astichi.model import Composable, ComposableDescription, ComposableHole, TargetAddress

__all__ = [
    "__version__",
    "Composable",
    "ComposableDescription",
    "ComposableHole",
    "TargetAddress",
    "build",
    "compile",
]
