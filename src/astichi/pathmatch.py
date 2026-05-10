"""Tuple path selector matching."""

from __future__ import annotations

from functools import lru_cache


def matches_path(selector: tuple[str, ...], path: tuple[str, ...]) -> bool:
    """Return whether ``selector`` matches ``path``.

    Selector operators:

    - ``"."`` matches exactly one path part
    - ``"?"`` matches zero or one path parts
    - ``"*"`` matches zero or more path parts
    - ``"+"`` matches one or more path parts

    Every other selector part is matched literally.
    """

    @lru_cache(maxsize=None)
    def matches_at(selector_index: int, path_index: int) -> bool:
        if selector_index == len(selector):
            return path_index == len(path)

        part = selector[selector_index]

        if part == ".":
            return path_index < len(path) and matches_at(
                selector_index + 1,
                path_index + 1,
            )

        if part == "?":
            return matches_at(selector_index + 1, path_index) or (
                path_index < len(path)
                and matches_at(selector_index + 1, path_index + 1)
            )

        if part == "*":
            return matches_at(selector_index + 1, path_index) or (
                path_index < len(path) and matches_at(selector_index, path_index + 1)
            )

        if part == "+":
            return path_index < len(path) and (
                matches_at(selector_index + 1, path_index + 1)
                or matches_at(selector_index, path_index + 1)
            )

        return (
            path_index < len(path)
            and part == path[path_index]
            and matches_at(selector_index + 1, path_index + 1)
        )

    return matches_at(0, 0)
