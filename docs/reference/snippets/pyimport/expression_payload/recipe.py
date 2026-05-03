"""Expression payload with a managed pyimport prefix."""


def run() -> str:
    root = astichi.compile(
        """
def f():
    return astichi_hole(value)
"""
    )
    payload = astichi.compile(
        """
astichi_pyimport(module=foo, names=(a,))
(a, 1)
"""
    )
    builder = astichi.build()
    builder.add.Root(root)
    builder.add.Payload(payload)
    builder.Root.value.add.Payload()
    return ast.unparse(builder.build().materialize().tree)
