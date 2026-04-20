"""Standard user-facing error string shape for Astichi diagnostics."""

from __future__ import annotations

VALID_PHASES: frozenset[str] = frozenset(
    ("compile", "unroll", "build", "materialize", "emit")
)

_DEFAULT_BUILD_PATH_HINT = (
    "check fluent ref spelling and that the instance is registered before "
    "deep traversal"
)


def format_astichi_error(
    phase: str,
    construct_problem: str,
    *,
    context: str | None = None,
    source: str | None = None,
    hint: str | None = None,
    provenance: str | None = None,
) -> str:
    """Return one line: ``<phase>: …`` with optional ``; label: …`` fields.

    Allowed field keys (in order): ``context``, ``source``, ``hint``, ``provenance``.
    """
    normalized = phase.strip().lower()
    if normalized not in VALID_PHASES:
        raise ValueError(
            f"phase must be one of {sorted(VALID_PHASES)}; got {phase!r}"
        )
    primary = f"{normalized}: {construct_problem.strip()}"
    parts: list[str] = [primary]
    for label, value in (
        ("context", context),
        ("source", source),
        ("hint", hint),
        ("provenance", provenance),
    ):
        if value:
            parts.append(f"{label}: {value}")
    return "; ".join(parts)


def default_build_path_hint() -> str:
    """Combined hint when registration vs spelling cannot be distinguished."""
    return _DEFAULT_BUILD_PATH_HINT
