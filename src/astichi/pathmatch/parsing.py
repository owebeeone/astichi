"""String parser for path selector tuples."""

from __future__ import annotations

from astichi.pathmatch.matching import RESERVED_CHARS


def parse_path_selector(text: str) -> tuple[str, ...]:
    """Parse ``/``-separated path selector text into selector parts.

    ``""`` is the empty selector. Non-empty selectors use ``/`` as the part
    separator. Parts are kept literally, including matcher operators such as
    ``"."``, ``"?"``, ``"*"`` and ``"+"``.
    """
    if text == "":
        return ()

    parts = tuple(text.split("/"))
    for part in parts:
        if part == "":
            raise ValueError("invalid path selector: empty path selector part")
        if part in RESERVED_CHARS:
            continue
        if any(char in RESERVED_CHARS for char in part):
            raise ValueError(
                f"invalid path selector: reserved path selector character in {part!r}"
            )
    return parts
