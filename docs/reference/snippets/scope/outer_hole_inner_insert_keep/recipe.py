"""Hole + insert shell + astichi_keep: inner `value` renamed; outer keep pins the outer name."""

def run() -> str:
    import ast

    import astichi

    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
value = 1
astichi_hole(target_slot)
result = astichi_keep(value)
"""
        )
    )
    builder.add.Inner(
        astichi.compile(
            """
value = 2
"""
        )
    )
    builder.Root.target_slot.add.Inner()
    return ast.unparse(builder.build().materialize().tree)
