"""Helpers for Python import-statement binding names."""

from __future__ import annotations

import ast


def import_alias_binding_name(
    alias: ast.alias,
    *,
    from_import: bool,
    include_star: bool = False,
) -> str | None:
    """Return the local name bound by one ordinary Python import alias."""
    if from_import:
        if alias.name == "*" and not include_star:
            return None
        return alias.asname or alias.name
    return alias.asname or alias.name.split(".")[0]


def import_statement_binding_names(
    node: ast.Import | ast.ImportFrom,
    *,
    include_star: bool = False,
) -> tuple[str, ...]:
    """Return the local binding names introduced by an import statement."""
    names: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            name = import_alias_binding_name(
                alias,
                from_import=False,
                include_star=include_star,
            )
            if name is not None:
                names.append(name)
        return tuple(names)
    for alias in node.names:
        name = import_alias_binding_name(
            alias,
            from_import=True,
            include_star=include_star,
        )
        if name is not None:
            names.append(name)
    return tuple(names)
