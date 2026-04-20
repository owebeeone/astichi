"""Hole + insert shell + astichi_keep: inner `value` renamed; outer keep pins the outer name."""

def run() -> str:
    import ast

    import astichi

    compiled = astichi.compile(
        """
value = 1
astichi_hole(target_slot)

@astichi_insert(target_slot)
def inner():
    value = 2

result = astichi_keep(value)
"""
    )
    return ast.unparse(compiled.materialize().tree)
