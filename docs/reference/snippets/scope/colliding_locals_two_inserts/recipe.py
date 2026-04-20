"""Two block contributions with the same local name; hygiene renames one (isolated scopes)."""

def run() -> str:
    import ast

    import astichi

    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.add.StepA(astichi.compile("total = 0\n"))
    builder.add.StepB(astichi.compile("total = 1\n"))
    builder.Root.body.add.StepA(order=0)
    builder.Root.body.add.StepB(order=1)
    return ast.unparse(builder.build().materialize().tree)
