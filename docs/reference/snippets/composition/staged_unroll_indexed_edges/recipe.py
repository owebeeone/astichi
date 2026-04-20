"""Stage-1 merge loop+root; stage-2 attach per-iteration steps; unroll on second build().

The root shell holds ``events = []`` and a ``body`` hole; the loop fragment carries
``astichi_for`` and a per-iteration ``step`` hole. Stage 2 registers ``Step0`` …
``Step2`` and wires each to **indexed** targets ``Pipeline.Loop.step[i]``. Those
paths exist only after ``astichi_for`` is expanded. The default ``build()`` uses
``unroll="auto"``, which unrolls whenever any edge targets an indexed path—so
explicit ``unroll=True`` is not required here (it would only force unroll even if
there were no indexed edges).

``step[0]`` is the **first iteration’s** block hole named ``step`` inside ``Loop``:
the loop body declares ``astichi_hole(step)`` once, and unrolling the ``(1, 2, 3)``
domain produces one target per iteration—``step[0]``, ``step[1]``, ``step[2]``—so
each append insert wires to the matching iteration’s body.

Stage-2 inserts live **under** ``Pipeline`` / unrolled ``Loop`` bodies; ``events`` is
defined on the outer ``Root`` fragment. ``astichi_pass(events, outer_bind=True)``
requests a **same-name immediate outer bind**: the pass demand resolves to the
``events`` in the parent Astichi scope (same list as ``events = []`` on ``Root``).
Without ``outer_bind=True`` (or an explicit ``builder.assign`` / export–import path),
that nested boundary does not auto-resolve. Do not use bare statement-form
``astichi_pass(events); ...`` (rejected). Other options: export ``events`` from one
insert and ``astichi_import(events)`` in others, or use ``assign`` wiring.
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
            events = []
            astichi_hole(body)
            result = events
            """
        )
    )
    builder1.add.Loop(
        piece(
            """
            for x in astichi_for((1, 2, 3)):
                astichi_hole(step)
            """
        )
    )
    builder1.Root.body.add.Loop(order=0)
    composable1 = builder1.build()

    # Stage 2: embed composable1; one insert per loop iteration (indexed step targets).
    # outer_bind=True on each pass: bind `events` to Root’s `events` (nested insert → outer scope).
    builder2: BuilderHandle = astichi.build()
    builder2.add.Pipeline(composable1)

    builder2.add.Step0(
        piece(
            """
            astichi_pass(events, outer_bind=True).append("first")
            """
        )
    )
    # Loop iteration 0: hole `step` → `step[0]` after astichi_for unroll (see docstring).
    builder2.Pipeline.Loop.step[0].add.Step0(order=0)

    builder2.add.Step1(
        piece(
            """
            # Imports the events list from the outer scope.
            astichi_import(events, outer_bind=True)
            events.append("second")
            """
        )
    )
    builder2.Pipeline.Loop.step[1].add.Step1(order=1)

    builder2.add.Step2(
        piece(
            """
            # Creates a local scope copy of events.
            events = astichi_pass(events, outer_bind=True)
            events.append("third")
            """
        )
    )
    builder2.Pipeline.Loop.step[2].add.Step2(order=2)

    composable2 = builder2.build()
    return ast.unparse(composable2.materialize().tree)
