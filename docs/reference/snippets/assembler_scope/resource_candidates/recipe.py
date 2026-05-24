"""Use assembler resources and selectors to fill an Astichi builder graph."""


def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi import Composable
    from astichi.assembler import (
        AssemblyScope,
        as_composable,
        as_external_value,
        as_identifier,
        find_candidates,
        require_one,
    )

    def piece(source: str) -> Composable:
        return astichi.compile(textwrap.dedent(source).strip() + "\n")

    root = piece(
        """
        class class_name__astichi_arg__:
            default = astichi_bind_external(default_value)

            def method_name__astichi_arg__(self, params__astichi_param_hole__):
                result = []
                astichi_hole(body)
                return result
        """
    )
    params = piece(
        """
        def astichi_params(item):
            pass
        """
    )
    body = piece(
        """
        astichi_pass(result, outer_bind=True).append(astichi_bind_external(delta))
        """
    )

    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    def apply_one(
        resource,
        *,
        name: str,
        build_match: tuple[str, ...],
        owner_match: tuple[str, ...] | None = None,
    ) -> None:
        scope.apply(
            require_one(
                find_candidates(
                    scope.inventory,
                    resource,
                    name=name,
                    build_match=build_match,
                    owner_match=owner_match,
                )
            )
        )

    apply_one(as_identifier("GeneratedGetter"), name="class_name", build_match=("Root",))
    apply_one(
        as_identifier("fetch"),
        name="method_name",
        build_match=("Root",),
        owner_match=("GeneratedGetter",),
    )
    apply_one(
        as_external_value(42),
        name="default_value",
        build_match=("Root",),
        owner_match=("GeneratedGetter",),
    )
    apply_one(
        as_composable(params, build_name="GetterParams"),
        name="params",
        build_match=("Root",),
        owner_match=("GeneratedGetter", "fetch"),
    )
    apply_one(
        as_composable(body, build_name="GetterBody", build_index=1, order=0),
        name="body",
        build_match=("Root",),
        owner_match=("GeneratedGetter", "fetch"),
    )
    apply_one(
        as_external_value(9),
        name="delta",
        build_match=("Root", "GetterBody[1]"),
    )

    return ast.unparse(scope.build().materialize().tree)
