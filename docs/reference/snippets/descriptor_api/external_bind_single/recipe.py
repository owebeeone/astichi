"""Discover and satisfy external binds from a single composable descriptor.

The descriptor API reports ``astichi_bind_external(...)`` demands before
materialization. A tool can inspect ``description.external_binds``, gather values
from data records, bind only the required names, and then materialize the
single composable.
"""


def run() -> str:
    import ast
    import textwrap

    import astichi
    from astichi import Composable

    def piece(src: str) -> Composable:
        return astichi.compile(textwrap.dedent(src).strip() + "\n")

    template = piece(
        """
        label = astichi_bind_external(label)
        suffix = astichi_bind_external(suffix)
        result = f"{label}:{suffix}"
        """
    )

    values = {"label": "descriptor", "suffix": "bound"}
    description = template.describe()
    bind_values = {
        bind.name: values[bind.name]
        for bind in description.external_binds
        if not bind.already_bound
    }

    bound = template.bind(bind_values)
    assert all(bind.already_bound for bind in bound.describe().external_binds)
    return ast.unparse(bound.materialize().tree)
