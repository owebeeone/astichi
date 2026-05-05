"""Render astichi_comment markers as final Python comments."""


def run() -> str:
    import textwrap

    import astichi

    root = astichi.compile(
        textwrap.dedent(
            """
            def collect(row, enabled):
                astichi_comment("generated from {__file__}:{__line__} {field_name}")
                rows = []
                astichi_hole(body)
                if enabled:
                    astichi_hole(empty)
                return rows
            """
        ).strip()
        + "\n",
        file_name="snippets/comment/root.py",
        line_number=10,
    )
    body = astichi.compile(
        textwrap.dedent(
            """
            astichi_comment("normalize row\\nthen append it")
            astichi_pass(rows, outer_bind=True).append(
                dict(astichi_pass(row, outer_bind=True))
            )
            """
        ).strip()
        + "\n",
        file_name="snippets/comment/body.py",
        line_number=20,
    )
    empty = astichi.compile(
        'astichi_comment("nothing to do\\nhere")\n',
        file_name="snippets/comment/empty.py",
        line_number=30,
    )

    builder = astichi.build()
    builder.add.Root(root)
    builder.add.Body(body)
    builder.add.Empty(empty)
    builder.Root.body.add.Body()
    builder.Root.empty.add.Empty()
    return builder.build().emit_commented()
