from __future__ import annotations

import astichi
from astichi.placeholder import astichi as astichi_fn


def test_astichi_exported_from_package() -> None:
    assert astichi.astichi() is True


def test_astichi_placeholder_module() -> None:
    assert astichi_fn() is True
