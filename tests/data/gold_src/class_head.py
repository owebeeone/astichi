"""Class-head expression holes cover bases and class keywords."""

from __future__ import annotations

import re

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
class SingleBase(astichi_hole(single_base)):
    pass


class MultiBase(*astichi_hole(multi_bases)):
    pass


class WithMeta(BaseRoot, metaclass=astichi_hole(meta)):
    pass


class WithKeywords(BaseRoot, **astichi_hole(class_keywords)):
    pass
""",
            file_name="gold_src/class_head.py",
        )
    )
    builder.add.BaseRoot(
        astichi.compile("BaseRoot\n", file_name="gold_src/class_head.py")
    )
    builder.add.BaseA(astichi.compile("BaseA\n", file_name="gold_src/class_head.py"))
    builder.add.BaseB(astichi.compile("BaseB\n", file_name="gold_src/class_head.py"))
    builder.add.Meta(astichi.compile("Meta\n", file_name="gold_src/class_head.py"))
    builder.add.Keywords(
        astichi.compile(
            """
{metaclass: Meta, flag: True}
""",
            file_name="gold_src/class_head.py",
        )
    )
    builder.Root.single_base.add.BaseRoot()
    builder.Root.multi_bases.add.BaseA(order=0)
    builder.Root.multi_bases.add.BaseB(order=1)
    builder.Root.meta.add.Meta()
    builder.Root.class_keywords.add.Keywords()
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    class Meta(type):
        def __new__(
            mcls: type,
            name: str,
            bases: tuple[type, ...],
            namespace: dict[str, object],
            **kwargs: object,
        ) -> type:
            cls = super().__new__(mcls, name, bases, namespace)
            for key, value in kwargs.items():
                setattr(cls, key, value)
            return cls

    namespace = {
        "BaseRoot": type("BaseRoot", (), {}),
        "BaseA": type("BaseA", (), {}),
        "BaseB": type("BaseB", (), {}),
        "Meta": Meta,
    }
    for name in re.findall(r"\bBaseRoot__astichi_scoped_\d+\b", materialized_source):
        namespace[name] = namespace["BaseRoot"]
    for name in re.findall(r"\bMeta__astichi_scoped_\d+\b", materialized_source):
        namespace[name] = namespace["Meta"]
    exec(compile(materialized_source, "<class_head>", "exec"), namespace)  # noqa: S102
    assert namespace["SingleBase"].__bases__ == (namespace["BaseRoot"],)
    assert namespace["MultiBase"].__bases__ == (
        namespace["BaseA"],
        namespace["BaseB"],
    )
    assert isinstance(namespace["WithMeta"], namespace["Meta"])
    assert isinstance(namespace["WithKeywords"], namespace["Meta"])
    assert namespace["WithKeywords"].flag is True
    assert "astichi_hole" not in materialized_source
    assert "astichi_insert" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("class_head.py", build_case, validate_case))
