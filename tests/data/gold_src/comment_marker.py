from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    root = astichi.compile(
        'astichi_comment("root {__file__}:{__line__} {field_name}")\n'
        "items = {}\n"
        "astichi_hole(body)\n"
        "if enabled:\n"
        "    astichi_hole(empty)\n",
        file_name="gold_src/comment_marker_root.py",
        line_number=10,
    )
    body = astichi.compile(
        'astichi_comment("body from {__file__}:{__line__}\\nsecond line")\n'
        'items["x"] += 1\n',
        file_name="gold_src/comment_marker_body.py",
        line_number=20,
    )
    empty = astichi.compile(
        'astichi_comment("nothing to do\\nhere")\n',
        file_name="gold_src/comment_marker_empty.py",
        line_number=30,
    )

    builder = astichi.build()
    builder.add.Root(root)
    builder.add.Body(body)
    builder.add.Empty(empty)
    builder.Root.body.add.Body()
    builder.Root.empty.add.Empty()
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: astichi.Composable,
    pre_source: str,
    materialized_source: str,
) -> None:
    del composable
    executable_source = materialized.emit(provenance=False)
    assert "astichi_comment" in pre_source
    assert "astichi_comment" not in executable_source
    assert "# root gold_src/comment_marker_root.py:10 {field_name}" in materialized_source
    assert "# body from gold_src/comment_marker_body.py:20" in materialized_source
    assert "# here" in materialized_source
    compile(materialized_source, "goldens/materialized/comment_marker.py", "exec")


if __name__ == "__main__":
    raise SystemExit(
        run_case(
            "comment_marker.py",
            build_case,
            validate_case,
            emit_commented=True,
        )
    )
