"""Stage-1 merge loop+root; stage-2 attach per-iteration steps; unroll on second build().

The root shell holds ``events = []`` and a ``body`` hole; the loop fragment carries
``astichi_for`` and a per-iteration ``step`` hole. Stage 2 registers ``Step0`` …
``Step2`` and wires each to **indexed** targets ``Pipeline.Root.Loop.step[i]``. Those
paths exist only after ``astichi_for`` is expanded. The default ``build()`` uses
``unroll="auto"``, which unrolls whenever any edge targets an indexed path—so
explicit ``unroll=True`` is not required here (it would only force unroll even if
there were no indexed edges).

``step[0]`` is the **first iteration’s** block hole named ``step`` inside ``Loop``:
the loop body declares ``astichi_hole(step)`` once, and unrolling the ``(1, 2, 3)``
domain produces one target per iteration—``step[0]``, ``step[1]``, ``step[2]``—so
each append insert wires to the matching iteration’s body.

Stage-2 inserts live **under** ``Pipeline.Root`` / unrolled ``Loop`` bodies; ``events`` is
defined on the outer ``Root`` fragment. The explicit threading story is:

- ``Loop`` imports ``events`` from ``Root``
- ``Step0`` imports ``events`` and is wired explicitly with ``builder.assign``
- ``Step1`` imports ``events`` from its immediate enclosing ``Loop`` via ``outer_bind=True``
- ``Step2`` uses value-form ``astichi_pass(events, outer_bind=True)`` to alias Loop's
  imported ``events`` locally before appending

The middle ``Loop`` import is now required for the nested ``outer_bind=True`` cases:
the child step resolves against its immediate enclosing Astichi scope, not by
searching outward. Do not use bare statement-form
``astichi_pass(events); ...`` (rejected).
"""

def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi.builder import BuilderHandle
    from astichi import Composable

    def piece(src: str) -> Composable:
        return astichi.compile(textwrap.dedent(src).strip() + "\n")

    # Stage 1: root + loop; first merge yields a composable with Loop.step[i] holes.
    builder1: BuilderHandle = astichi.build()
    builder1.add.Root(
        piece(
            """
            # Root owns the concrete `events` binding for this composition.
            events = []
            astichi_hole(body)
            result = events
            """
        )
    )
    builder1.add.Loop(
        piece(
            """
            # imports events from Root so nested steps can resolve through Loop.
            astichi_import(events, outer_bind=True)
            for x in astichi_for((1, 2, 3)):
                astichi_hole(step)
            """
        )
    )
    # Root.body ← Loop (single child in the body hole).
    builder1.Root.body.add.Loop(order=0)
    composable1 = builder1.build()  # Merged Root+Loop; unroll happens on stage-2 build.

    # Stage 2: embed composable1; one insert per loop iteration (indexed step targets).
    # Each step imports `events` from its immediate enclosing Loop scope.
    builder2: BuilderHandle = astichi.build()
    # Pipeline wraps the stage-1 composable as one insert target.
    builder2.add.Pipeline(composable1)

    builder2.add.Step0(
        piece(
            """
            # Explicit builder.assign below binds this import to Pipeline.Root.events.
            astichi_import(events)
            events.append("first")
            """
        )
    )
    # Loop iteration 0: hole `step` → `step[0]` after astichi_for unroll (see docstring).
    builder2.Pipeline.Root.Loop.step[0].add.Step0(order=0)

    builder2.add.Step1(
        piece(
            """
            # outer_bind=True resolves to Loop's imported `events`.
            astichi_import(events, outer_bind=True)
            events.append("second")
            """
        )
    )
    # step[1]: second unrolled iteration.
    builder2.Pipeline.Root.Loop.step[1].add.Step1(order=1)

    builder2.add.Step2(
        piece(
            """
            # outer_bind=True resolves pass() through Loop, then aliases locally.
            events = astichi_pass(events, outer_bind=True)
            events.append("third")
            """
        )
    )
    # step[2]: third unrolled iteration.
    builder2.Pipeline.Root.Loop.step[2].add.Step2(order=2)

    # Step0 uses bare import; wire its demand to Pipeline.Root’s `events` supply.
    builder2.assign.Step0.events.to().Pipeline.Root.events

    composable2 = builder2.build()  # Indexed edges → default unroll="auto" runs unroll.
    return ast.unparse(composable2.materialize().tree)
