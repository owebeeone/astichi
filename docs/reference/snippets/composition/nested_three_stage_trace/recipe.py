"""Compose a prior merge into a larger graph twice: leaf → middle → root with trace wiring.

A bare ``astichi_hole(body)`` only makes sense once the builder attaches **multiple**
inserts into ``Root.body`` (here ``First`` and ``Second`` with explicit order).

Stage 2 embeds the same composable **twice** under ``astichi_hole(head)`` and
``astichi_hole(tail)``. Leaf inserts use a shared local name (``leaf_tag``) so
materialization shows hygiene renames (``leaf_tag__astichi_scoped_*``) when the
same subgraph is merged in multiple places.

Value-form ``astichi_pass(trace).append(...)`` is wired later through the staged
``builder.assign...`` edges onto the root ``trace = []``. Do not use
``astichi_pass(trace); trace = []`` (rejected). Alternative: export ``trace``
from one insert and ``astichi_import(trace)`` in others, or use
``outer_bind=True`` only for a same-name immediate enclosing scope bind.
"""

def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi.builder import BuilderHandle
    from astichi import Composable

    def piece(src: str) -> Composable:
        return astichi.compile(textwrap.dedent(src).strip() + "\n")

    # Stage 1: leaf → middle
    builder1: BuilderHandle = astichi.build()
    # defines Root instance
    builder1.add.Root(
        piece(
            """
            astichi_hole(body)
            """
        )
    )
    # defines First instance
    builder1.add.First(
        piece(
            """
            leaf_tag = "leaf-a" # leaf_tag is scoped to First instance
            astichi_pass(trace).append(leaf_tag)
            """
        )
    )
    # defines Second instance
    builder1.add.Second(
        piece(
            """
            leaf_tag = "leaf-b" # leaf_tag is scoped to Second instance
            astichi_pass(trace).append(leaf_tag)
            """
        )
    )
    # wires First instance to Root.body
    builder1.Root.body.add.First(order=0)
    # wires Second instance to Root.body
    builder1.Root.body.add.Second(order=1)
    # builds the first composable
    composable1 = builder1.build()

    # Stage 2: middle → root (same composable twice: head then tail)
    builder2: BuilderHandle = astichi.build()
    builder2.add.Middle(
        piece(
            """
            astichi_hole(head)
            astichi_hole(tail)
            """
        )
    )
    builder2.add.Head(composable1)
    builder2.add.Tail(composable1)
    # same order means stable order within each hole.
    builder2.Middle.head.add.Head(order=0)
    builder2.Middle.tail.add.Tail(order=0)
    composable2 = builder2.build()

    # Stage 3: root
    builder3: BuilderHandle = astichi.build()
    builder3.add.Root(
        piece(
            """
            trace = []
            astichi_hole(body)
            result = trace
            """
        )
    )
    builder3.add.Pipeline(composable2)
    builder3.Root.body.add.Pipeline(order=0)
    # wires Pipeline instance to Root.body
    builder3.assign.Pipeline.trace.to().Root.trace
    return ast.unparse(builder3.build().materialize().tree)
