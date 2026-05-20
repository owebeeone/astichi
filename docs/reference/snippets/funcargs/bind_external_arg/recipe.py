"""Bind-external funcargs: ``astichi_bind_external(seed)`` inside ``astichi_funcargs``, resolved
by ``.bind(seed=…)`` on the merged composable before ``materialize()``.

This recipe is one module with **several** call sites:

- **``result_combined``** — ``**kwargs`` hole carrying ``astichi_bind_external``; other holes use
  literals.
- **``result_plain`` / ``result_star`` / ``result_kw``** — literals only (``20``, ``7``,
  ``msg="solo"``) on a single hole each.
- **``result_plain_scoped`` / ``result_star_scoped`` / ``result_kw_scoped``** — one hole each:
  ``astichi_import`` + walrus + ``astichi_export``, or ``astichi_pass`` on the walrus RHS for the
  star case, with ``builder.assign`` from composable handles to names on ``Root``.
- **``result_multi_scope``** — **one** function call with ``astichi_hole(head)``,
  ``astichi_hole(varargs)``, and ``astichi_hole(kwargs)``; each payload is its own Astichi scope
  (hygiene may rename ``out`` across scopes, e.g. ``out__astichi_scoped_*``; ``builder.assign``
  threads each Root-side pass slot onto the correct exported ``out``).
- **``result_kw_parameterized``** — a single parameterized
  ``astichi_funcargs(param__astichi_arg__=astichi_pass(value__astichi_arg__, outer_bind=True))``
  payload looped into ``builder.add.KwParam[i](..., arg_names={"param": ..., "value": ...})``
  with matching ``builder.Root.kw_parameterized.add.KwParam[i]()`` edge adds. The subscript form
  spawns one distinct instance per iteration; each edge-local ``arg_names`` overlay resolves both
  the keyword **name** and the identifier passed through to the outer scope before merge.
  ``outer_bind=True`` threads the resolved value identifier (``v1`` / ``v2`` / ``v3``) to the
  same-name local on ``Root`` without an explicit ``builder.assign`` wire; the resulting call is
  ``func_kw(a=v1, b=v2, c=v3)``.
- **``result_kw_ref``** — same shape, but the keyword **value** uses
  ``astichi_ref(external=value_path)`` instead of an ``__astichi_arg__`` identifier slot. The
  edge supplies the compile-time path with ``bind={"value_path": "vals.v1"}``; ``astichi_ref``
  lowers that string into a real ``Name``/``Attribute`` chain at materialize time. A single
  ``_=astichi_import(vals)`` declaration threads the stable namespace root across the
  contribution-shell boundary, so the per-instance varying ``.v1`` / ``.v2`` / ``.v3`` attribute
  tails are unambiguous attribute lookups (not free names subject to hygiene). Resulting call:
  ``func_kw(a=vals.v1, b=vals.v2, c=vals.v3)``.
"""

def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi.builder import BuilderHandle
    from astichi import Composable

    def piece(src: str) -> Composable:
        return astichi.compile(textwrap.dedent(src).strip() + "\n")

    bind_carrier = piece(
        """
        astichi_funcargs(**{"seed": astichi_bind_external(seed)})
        """
    )
    kw_name = piece(
        """
        astichi_funcargs(name="x")
        """
    )
    kw_flag = piece(
        """
        astichi_funcargs(flag=True)
        """
    )
    parametric_kwarg = piece(
        """
        astichi_funcargs(
            param__astichi_arg__=astichi_pass(value__astichi_arg__, outer_bind=True),
        )
        """
    )
    parametric_ref_kwarg = piece(
        """
        astichi_funcargs(
            param__astichi_arg__=astichi_ref(external=value_path),
            _=astichi_import(vals),
        )
        """
    )

    builder: BuilderHandle = astichi.build()
    builder.add.Root(
        piece(
            """
            def func_combined(head, *args, **kwds):
                return (head, args, kwds)

            def func_plain(*args, **kwds):
                return (args, kwds)

            def func_star(*args):
                return args

            def func_kw(**kwds):
                return kwds

            def func_one(head, *args, **kwds):
                return (head, args, kwds)

            source_plain_scoped = 100
            seed_star_scoped = 200
            source_kw_scoped = 300
            head_supply = 1
            seed_star = 2
            v1 = 10
            v2 = 20
            v3 = 30

            class vals:
                v1 = 100
                v2 = 200
                v3 = 300

            result_combined = func_combined(
                astichi_hole(head),
                *astichi_hole(varargs),
                fixed=1,
                **astichi_hole(kwargs),
            )
            result_plain = func_plain(astichi_hole(plain_args), fixed=2)
            result_star = func_star(*astichi_hole(star_only))
            result_kw = func_kw(fixed=4, **astichi_hole(kw_only))

            result_plain_scoped = func_plain(astichi_hole(plain_args_scoped), fixed=2)
            result_star_scoped = func_star(*astichi_hole(star_only_scoped))
            result_kw_scoped = func_kw(fixed=4, **astichi_hole(kw_only_scoped))

            result_multi_scope = func_one(
                astichi_hole(head_ms),
                *astichi_hole(varargs_ms),
                fixed=1,
                **astichi_hole(kwargs_ms),
            )
            result_kw_parameterized = func_kw(**astichi_hole(kw_parameterized))
            result_kw_ref = func_kw(**astichi_hole(kw_ref))
            out_multi_scope = astichi_pass(out_multi_scope)
            out_kw_scoped = astichi_pass(out_kw_scoped)
            out_star_scoped = astichi_pass(out_star_scoped)
            out_plain_scoped = astichi_pass(out_plain_scoped)
            """
        )
    )

    # --- result_combined
    builder.add.HeadCombined(
        piece(
            """
            astichi_funcargs("head_slot")
            """
        )
    )
    builder.add.VarCombined(
        piece(
            """
            astichi_funcargs(2)
            """
        )
    )
    builder.add.SeedDictCombined(bind_carrier)
    builder.add.KwNameCombined(kw_name)
    builder.add.KwFlagCombined(kw_flag)
    builder.Root.head.add.HeadCombined(order=0)
    builder.Root.varargs.add.VarCombined(order=0)
    builder.Root.kwargs.add.SeedDictCombined(order=0)
    builder.Root.kwargs.add.KwNameCombined(order=1)
    builder.Root.kwargs.add.KwFlagCombined(order=2)

    # --- literals: plain / star / kw
    builder.add.Plain(
        piece(
            """
            astichi_funcargs(20)
            """
        )
    )
    builder.Root.plain_args.add.Plain(order=0)

    builder.add.Star(
        piece(
            """
            astichi_funcargs(7)
            """
        )
    )
    builder.Root.star_only.add.Star(order=0)

    builder.add.KwSolo(
        piece(
            """
            astichi_funcargs(msg="solo")
            """
        )
    )
    builder.Root.kw_only.add.KwSolo(order=0)

    # --- scoped single-hole: plain / star / kw
    builder.add.PlainScoped(
        piece(
            """
            astichi_funcargs(
                (out := seed),
                _=astichi_import(seed),
                _=astichi_export(out),
            )
            """
        )
    )
    builder.Root.plain_args_scoped.add.PlainScoped(order=0)
    builder.assign.PlainScoped.seed.to().Root.source_plain_scoped

    builder.add.StarScoped(
        piece(
            """
            astichi_funcargs(
                (out := astichi_pass(seed)),
                _=astichi_export(out),
            )
            """
        )
    )
    builder.Root.star_only_scoped.add.StarScoped(order=0)
    builder.assign.StarScoped.seed.to().Root.seed_star_scoped

    builder.add.KwScoped(
        piece(
            """
            astichi_funcargs(
                msg=(out := seed),
                _=astichi_import(seed),
                _=astichi_export(out),
            )
            """
        )
    )
    builder.Root.kw_only_scoped.add.KwScoped(order=0)
    builder.assign.KwScoped.seed.to().Root.source_kw_scoped

    # --- one call, multiple holes (separate composable instances from result_combined)
    builder.add.HeadMulti(
        piece(
            """
            astichi_funcargs(
                (out := seed),
                _=astichi_import(seed),
                _=astichi_export(out),
            )
            """
        )
    )
    builder.add.VarMulti(
        piece(
            """
            astichi_funcargs(
                (out := astichi_pass(seed)),
                _=astichi_export(out),
            )
            """
        )
    )
    builder.add.SeedDictMulti(bind_carrier)
    builder.add.KwNameMulti(kw_name)
    builder.add.KwFlagMulti(kw_flag)
    builder.Root.head_ms.add.HeadMulti(order=0)
    builder.Root.varargs_ms.add.VarMulti(order=0)
    builder.Root.kwargs_ms.add.SeedDictMulti(order=0)
    builder.Root.kwargs_ms.add.KwNameMulti(order=1)
    builder.Root.kwargs_ms.add.KwFlagMulti(order=2)
    builder.assign.HeadMulti.seed.to().Root.head_supply
    builder.assign.VarMulti.seed.to().Root.seed_star
    builder.assign.Root.out_multi_scope.to().HeadMulti.out
    builder.assign.Root.out_kw_scoped.to().KwScoped.out
    builder.assign.Root.out_star_scoped.to().StarScoped.out
    builder.assign.Root.out_plain_scoped.to().PlainScoped.out

    # --- parameterized kw: reuse one payload with edge-local arg_names
    param_values = (('a', 'v1'), ('b', 'v2'), ('c', 'v3'))
    for i, (param, value) in enumerate(param_values):
        builder.add.KwParam[i](parametric_kwarg, arg_names={"param": param, "value": value})
        builder.Root.kw_parameterized.add.KwParam[i]()

    # --- parameterized kw via astichi_ref: keyword name via __astichi_arg__,
    # keyword value via astichi_ref(external=...) lowering an edge-bound path
    for i, (param, attr) in enumerate(param_values):
        builder.add.KwRef[i](parametric_ref_kwarg, arg_names={"param": param})
        builder.Root.kw_ref.add.KwRef[i](bind={"value_path": f"vals.{attr}"})

    composable = builder.build()
    return ast.unparse(composable.bind(seed={"seed": 101}).materialize().tree)
