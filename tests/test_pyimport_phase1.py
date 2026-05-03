from __future__ import annotations

import pytest

import astichi
from astichi.lowering import MARKERS_BY_NAME


def test_pyimport_marker_is_registered() -> None:
    marker = MARKERS_BY_NAME["astichi_pyimport"]

    assert marker.source_name == "astichi_pyimport"
    assert marker.is_permitted_in_unroll_body() is False


def test_materialize_emits_basic_pyimport() -> None:
    compiled = astichi.compile(
        """
astichi_pyimport(module=foo, names=(a, b))
value = a()
"""
    )

    pyimports = [
        marker for marker in compiled.markers if marker.source_name == "astichi_pyimport"
    ]
    assert len(pyimports) == 1
    assert "a" in compiled.classification.locals
    assert "b" in compiled.classification.locals
    assert "a" not in compiled.classification.unresolved_free

    assert compiled.materialize().emit(provenance=False) == (
        "from foo import a, b\nvalue = a()\n"
    )


@pytest.mark.parametrize(
    ("source", "match"),
    [
        ("astichi_pyimport(names=(a,))\n", "requires module"),
        ("astichi_pyimport(module=foo, names=[])\n", "names= must be"),
        ("astichi_pyimport(module=foo, names=())\n", "must not be empty"),
        ("astichi_pyimport(module=foo, names=(a, a))\n", "duplicate"),
        ("astichi_pyimport(module=foo, names=(foo.a,))\n", "bare identifiers"),
        ("astichi_pyimport(module=foo, names={a: b})\n", "alias dict"),
        ("astichi_pyimport(module=foo, names=(a,), as_=b)\n", "may not combine"),
        ("astichi_pyimport(module=foo, as_='bar')\n", "as_= must be"),
        ("astichi_pyimport(module=foo.bar)\n", "dotted plain imports require"),
        ("astichi_pyimport(module=__future__, names=(annotations,))\n", "__future__"),
        ("astichi_pyimport(module='foo', names=(a,))\n", "module= must be"),
        (
            "astichi_pyimport(module=astichi_ref('1foo'), names=(a,))\n",
            "valid path",
        ),
    ],
)
def test_compile_rejects_invalid_pyimport_shapes(source: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        astichi.compile(source)


def test_compile_accepts_dynamic_module_ref_with_external_bind_prefix() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(module_path)
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))
value = thing()
"""
    )

    assert [marker.source_name for marker in compiled.markers] == [
        "astichi_bind_external",
        "astichi_pyimport",
        "astichi_ref",
        "astichi_bind_external",
    ]


def test_materialize_emits_dynamic_module_ref_after_binding() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(module_path)
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))
value = thing()
"""
    ).bind(module_path="pkg.mod")

    assert compiled.materialize().emit(provenance=False) == (
        "from pkg.mod import thing\nvalue = thing()\n"
    )


def test_materialize_emits_plain_alias_and_plain_no_alias() -> None:
    compiled = astichi.compile(
        """
astichi_pyimport(module=numpy, as_=np)
astichi_pyimport(module=os)
value = (np.array([1]), os.getcwd())
"""
    )

    assert compiled.materialize().emit(provenance=False) == (
        "import numpy as np\nimport os\nvalue = (np.array([1]), os.getcwd())\n"
    )


def test_materialize_aliases_import_after_hygiene_collision() -> None:
    compiled = astichi.compile(
        """
a = 1
astichi_hole(slot)

@astichi_insert(slot)
def shell():
    astichi_pyimport(module=foo, names=(a,))
    value = a()
""",
        source_kind="astichi-emitted",
    )

    assert compiled.materialize().emit(provenance=False) == (
        "from foo import a as a__astichi_scoped_1\n"
        "a = 1\n"
        "value = a__astichi_scoped_1()\n"
    )


def test_materialize_inserts_after_docstring_and_future_import() -> None:
    compiled = astichi.compile(
        '''"""Module docs."""
from __future__ import annotations
astichi_pyimport(module=foo, names=(a,))
value: a
'''
    )

    assert compiled.materialize().emit(provenance=False) == (
        '"""Module docs."""\n'
        "from __future__ import annotations\n"
        "from foo import a\n"
        "value: a\n"
    )


def test_pyimport_prefix_interleaves_before_astichi_import() -> None:
    compiled = astichi.compile(
        """
astichi_pyimport(module=foo, names=(a,))
astichi_import(dep)
value = a(dep)
"""
    )

    assert [marker.source_name for marker in compiled.markers[:2]] == [
        "astichi_pyimport",
        "astichi_import",
    ]


def test_compile_rejects_late_pyimport_statement() -> None:
    with pytest.raises(ValueError, match="top-of-Astichi-scope prefix"):
        astichi.compile(
            """
value = 1
astichi_pyimport(module=foo, names=(a,))
"""
        )


def test_compile_allows_pyimport_at_insert_shell_owner_scope_prefix() -> None:
    compiled = astichi.compile(
        """
@astichi_insert(slot)
def shell():
    astichi_pyimport(module=foo, names=(a,))
    value = a()
""",
        source_kind="astichi-emitted",
    )

    assert any(marker.source_name == "astichi_pyimport" for marker in compiled.markers)


def test_compile_rejects_pyimport_nested_inside_real_function_body() -> None:
    with pytest.raises(ValueError, match="nested inside a real user-authored"):
        astichi.compile(
            """
def helper():
    astichi_pyimport(module=foo, names=(a,))
    return a()
"""
        )
