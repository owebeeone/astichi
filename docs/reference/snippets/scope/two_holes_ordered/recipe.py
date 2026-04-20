"""Multiple named holes on the root; two insertions; distinct bindings (a vs b)."""

def run() -> str:
    import ast

    import astichi

    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(setup)\nastichi_hole(body)\n"))
    builder.add.Setup(astichi.compile("a = 10\n"))
    builder.add.Step(astichi.compile("b = 20\n"))
    builder.Root.setup.add.Setup()
    builder.Root.body.add.Step()
    return ast.unparse(builder.build().materialize().tree)
