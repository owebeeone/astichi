"""Tests for ``__astichi_arg__`` recognition in call-keyword-argument name slots.

These exercise a gap in the original issue 005 §1 coverage: call-site
keyword-argument names (``ast.keyword.arg``) were not scanned for the
``__astichi_arg__`` suffix, so authored payloads could not parameterise a
kwarg name the same way they parameterise a parameter name, an assignment
target, a def/class name, or a ``Name`` load.

The tests are written TDD-style: they are expected to fail against the
pre-fix codebase with the ``bind_identifier`` "no such slot" error and the
arg-gate failing to reject unresolved suffix occurrences in kwarg slots.
"""

from __future__ import annotations

import ast
import textwrap

import pytest

import astichi


def _compile(src: str) -> astichi.Composable:
    return astichi.compile(textwrap.dedent(src).strip() + "\n")


def test_arg_identifier_in_kwarg_name_resolves_via_bind_identifier() -> None:
    """``f(x__astichi_arg__=1)`` → bind_identifier → ``f(actual=1)``.

    The suffix lives in the keyword-argument name position of a plain
    ``Call``. The resolver must rewrite ``ast.keyword.arg`` the same way
    it rewrites ``ast.arg``.
    """
    compiled = _compile(
        """
        result = f(slot__astichi_arg__=1)
        """
    ).bind_identifier(slot="actual")

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert "__astichi_arg__" not in rendered
    assert "result = f(actual=1)" in rendered


def test_arg_identifier_in_kwarg_name_unresolved_rejects_at_materialize_gate() -> None:
    """Unresolved ``__astichi_arg__`` suffix in a kwarg name must fail the gate.

    The gate's walk must include ``ast.keyword`` so every suffix occurrence
    is surfaced in the diagnostic, not just the Name / arg / def cases.
    """
    compiled = _compile(
        """
        result = f(slot__astichi_arg__=1)
        """
    )

    with pytest.raises(ValueError) as excinfo:
        compiled.materialize()

    message = str(excinfo.value)
    assert "__astichi_arg__" in message
    assert "slot" in message


def test_arg_identifier_in_kwarg_name_accepts_compile_arg_names() -> None:
    """``compile(..., arg_names=...)`` should also resolve the kwarg slot."""
    compiled = astichi.compile(
        textwrap.dedent(
            """
            result = f(slot__astichi_arg__=1)
            """
        ).strip()
        + "\n",
        arg_names={"slot": "resolved"},
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert "__astichi_arg__" not in rendered
    assert "result = f(resolved=1)" in rendered


def test_arg_identifier_in_kwarg_name_bind_identifier_registers_slot() -> None:
    """``bind_identifier`` on the composable must accept the kwarg slot name.

    Before the fix this raises ``no __astichi_arg__ / astichi_import /
    astichi_pass slot named ...`` because the identifier-demand port is
    never registered for kwarg-name suffix occurrences.
    """
    compiled = _compile(
        """
        result = f(slot__astichi_arg__=1)
        """
    )

    # Should not raise.
    compiled.bind_identifier(slot="actual")


def test_arg_identifier_in_kwarg_name_survives_non_suffixed_kwargs() -> None:
    """Kwargs without the suffix must keep their authored names.

    After the fix, only suffixed kwarg names become identifier slots;
    plain kwargs like ``default=1`` remain verbatim.
    """
    compiled = _compile(
        """
        result = f(slot__astichi_arg__=1, keep=2)
        """
    ).bind_identifier(slot="actual")

    rendered = ast.unparse(compiled.materialize().tree)

    assert "__astichi_arg__" not in rendered
    assert "result = f(actual=1, keep=2)" in rendered


def test_arg_identifier_in_kwarg_name_in_funcargs_payload_resolves() -> None:
    """End-to-end: ``astichi_funcargs(slot__astichi_arg__=value)`` payload.

    Drives the feature through the real authored surface used for
    call-argument composition. After the fix, the kwarg-slot suffix
    resolves identically to any other identifier demand, and the merged
    call site emits a plain ``name=value`` kwarg.
    """
    root = _compile(
        """
        result = f(**astichi_hole(kwargs))
        """
    )
    payload = _compile(
        """
        astichi_funcargs(slot__astichi_arg__=1)
        """
    ).bind_identifier(slot="actual")

    builder = astichi.build()
    builder.add.Root(root)
    builder.add.Payload(payload)
    builder.Root.kwargs.add.Payload(order=0)
    composable = builder.build()

    rendered = ast.unparse(composable.materialize().tree)

    assert "__astichi_arg__" not in rendered
    assert "result = f(actual=1)" in rendered
