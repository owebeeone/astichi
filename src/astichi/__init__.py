"""astichi — AST composition for ahead-of-time Python codegen."""

__version__ = "0.1.0"

from astichi.builder import build
from astichi.frontend import compile
from astichi.model import Composable
from astichi.placeholder import astichi

__all__ = ["__version__", "Composable", "build", "compile", "astichi"]
