"""Single positional arg from astichi_bind_external(seed) inside funcargs; seed supplied via composable.bind."""

def run() -> str:
    import ast

    import astichi

    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func(value):
    return value

result = func(astichi_hole(args))
"""
        )
    )
    builder.add.Impl(astichi.compile("astichi_funcargs(astichi_bind_external(seed))\n"))
    builder.Root.args.add.Impl()
    built = builder.build()
    return ast.unparse(built.bind(seed=10).materialize().tree)
