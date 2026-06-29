"""Attach resources with ``AssemblyScope.wire(...)`` — one call per wire.

``wire(resource, **selector)`` is shorthand for
``apply(require_one(find_candidates(resource, **selector)))``: same structural
compatibility match, same refuse-on-ambiguity diagnostic. Here one polymorphic
``getter`` template is placed into the ``methods`` hole three times and
specialized per instance (a different method name and lookup key each time).
"""


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
    )

    def piece(source: str) -> Composable:
        return astichi.compile(textwrap.dedent(source).strip() + "\n")

    shell = piece(
        """
        class Accessors:
            def __init__(self, data):
                self._data = data
            astichi_hole(methods)
        """
    )
    getter = piece(
        """
        def method_name__astichi_arg__(self):
            return self._data[astichi_bind_external(key)]
        """
    )

    scope = AssemblyScope(astichi.build())
    scope.add("Shell", shell)

    for index, (method, key) in enumerate(
        (("get_name", "name"), ("get_email", "email"), ("get_age", "age")), start=1
    ):
        inst = f"Getter[{index}]"
        # Axis 1 — structure: place the same template into `methods`, repeatedly.
        scope.wire(
            as_composable(getter, build_name="Getter", build_index=index, order=index),
            name="methods",
        )
        # Axis 2 — specialization: bind this instance's name + key differently.
        scope.wire(as_identifier(method), name="method_name", build_match=("Shell", inst))
        scope.wire(as_external_value(key), name="key", build_match=("Shell", inst))

    return ast.unparse(scope.build().materialize().tree)
