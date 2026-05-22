"""AST helper utilities for Astichi."""

from astichi.asttools.shapes import (
    BLOCK,
    ELIF_CLAUSE,
    IDENTIFIER,
    NAMED_VARIADIC,
    PARAMETER,
    POSITIONAL_VARIADIC,
    SCALAR_EXPR,
    MarkerShape,
)
from astichi.asttools.imports import (
    import_alias_binding_name,
    import_statement_binding_names,
)
from astichi.asttools.clone import clone_ast
from astichi.asttools.inserts import (
    has_astichi_insert_decorator,
    is_astichi_insert_call,
    is_astichi_insert_shell,
    is_expression_insert_call,
)
from astichi.asttools.scopes import AstichiScope, AstichiScopeMap
from astichi.asttools.scope_keep import (
    add_astichi_scope_keep_names,
    astichi_scope_keep_names,
)

__all__ = [
    "AstichiScope",
    "AstichiScopeMap",
    "BLOCK",
    "ELIF_CLAUSE",
    "IDENTIFIER",
    "NAMED_VARIADIC",
    "PARAMETER",
    "POSITIONAL_VARIADIC",
    "SCALAR_EXPR",
    "MarkerShape",
    "add_astichi_scope_keep_names",
    "astichi_scope_keep_names",
    "clone_ast",
    "has_astichi_insert_decorator",
    "import_alias_binding_name",
    "import_statement_binding_names",
    "is_astichi_insert_call",
    "is_astichi_insert_shell",
    "is_expression_insert_call",
]
