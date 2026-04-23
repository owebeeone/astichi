"""Insert function parameters and bind body snippets to inserted parameter names.

Each target function uses ``<name>__astichi_param_hole__`` as the insertion
point. Each payload is a ``def astichi_params(...): pass`` carrier; only the
signature is inserted.
"""


def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi import Composable

    def piece(src: str) -> Composable:
        return astichi.compile(textwrap.dedent(src).strip() + "\n")

    typed_builder = astichi.build()
    # Parameter payload with an optional annotation hole filled in a prior stage.
    typed_builder.add.Params(
        piece(
            """
            def astichi_params(limit: astichi_hole(limit_type) = 10, *, debug=False):
                pass
            """
        )
    )
    typed_builder.add.Type(piece("int"))
    typed_builder.Params.limit_type.add.Type()

    builder = astichi.build()
    # Four independent functions exercise ordinary, typed, variadic, and scoped uses.
    builder.add.Root(
        piece(
            """
            def load(basic__astichi_param_hole__):
                return user

            def configure(typed__astichi_param_hole__):
                return limit, debug

            def collect(varargs__astichi_param_hole__):
                return items, options

            def run_request(request_params__astichi_param_hole__):
                astichi_hole(body)
                return session
            """
        )
    )
    # Adds a single ordinary parameter.
    builder.add.Basic(
        piece(
            """
            def astichi_params(user):
                pass
            """
        )
    )
    # Adds a typed/defaulted parameter plus a keyword-only parameter.
    builder.add.Typed(typed_builder.build())
    # Adds variadic parameter names; cardinality rules still allow only one of each.
    builder.add.Variadic(
        piece(
            """
            def astichi_params(*items, **options):
                pass
            """
        )
    )
    # Publishes session as a target-function parameter.
    builder.add.RequestParams(
        piece(
            """
            def astichi_params(session):
                pass
            """
        )
    )
    # Body snippets bind to inserted params explicitly, and locals still get hygiene.
    builder.add.Body(
        piece(
            """
            seen = astichi_pass(session, outer_bind=True)
            session = "local"
            local_session = session
            """
        )
    )

    builder.Root.basic.add.Basic(order=0)
    builder.Root.typed.add.Typed(order=0)
    builder.Root.varargs.add.Variadic(order=0)
    builder.Root.request_params.add.RequestParams(order=0)
    builder.Root.body.add.Body(order=0)
    return ast.unparse(builder.build().materialize().tree)
