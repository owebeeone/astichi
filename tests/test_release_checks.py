from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from scripts.release_checks import check_test_matrix, sync_version, verify_version


@pytest.fixture
def release_root(tmp_path: Path) -> Path:
    package = tmp_path / "src" / "astichi"
    package.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "astichi"\nversion = "1.1.2"\n', encoding="utf-8",
    )
    (package / "__init__.py").write_text(
        '"""Package docstring."""\n\n__version__ = "1.1.1"\n\nfrom astichi.builder import build\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "astichi"\nversion = "1.1.2"\n', encoding="utf-8",
    )
    return tmp_path


def test_sync_version_preserves_module_and_is_idempotent(release_root: Path) -> None:
    path = release_root / "src" / "astichi" / "__init__.py"
    original = path.read_text(encoding="utf-8")
    sync_version(release_root, "1.1.2")
    updated = path.read_text(encoding="utf-8")
    assert updated == original.replace('__version__ = "1.1.1"', "__version__ = '1.1.2'")
    sync_version(release_root, "1.1.2")
    assert path.read_text(encoding="utf-8") == updated
    verify_version(release_root, "1.1.2")


def test_sync_version_rejects_unprepared_manifest(release_root: Path) -> None:
    path = release_root / "src" / "astichi" / "__init__.py"
    original = path.read_bytes()
    with pytest.raises(ValueError, match="pyproject.toml must declare"):
        sync_version(release_root, "1.1.3")
    assert path.read_bytes() == original


@pytest.mark.parametrize("source", [
    'other = "1.1.1"\n',
    '__version__ = "1.1.1"\n__version__ = "1.1.0"\n',
    '__version__ = calculate_version()\n',
    '__version__ = alias = "1.1.1"\n',
    '__version__ = "1.1.1"; other = 1\n',
])
def test_sync_version_rejects_ambiguous_assignment(release_root: Path, source: str) -> None:
    path = release_root / "src" / "astichi" / "__init__.py"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="__version__"):
        sync_version(release_root, "1.1.2")
    assert path.read_text(encoding="utf-8") == source


def test_verify_version_does_not_repair_mirror(release_root: Path) -> None:
    path = release_root / "src" / "astichi" / "__init__.py"
    original = path.read_bytes()
    with pytest.raises(ValueError, match="astichi.__version__ must be"):
        verify_version(release_root, "1.1.2")
    assert path.read_bytes() == original


def test_verify_version_rejects_stale_lockfile(release_root: Path) -> None:
    sync_version(release_root, "1.1.2")
    path = release_root / "uv.lock"
    path.write_text('[[package]]\nname = "astichi"\nversion = "1.1.1"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="uv.lock must record"):
        verify_version(release_root, "1.1.2")


def test_test_matrix_builds_native_before_running_both_engines(
    release_root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_version(release_root, "1.1.2")
    monkeypatch.setenv("ASTICHI_SKIP_NATIVE_BUILD", "1")
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE_MATRIX", "0")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **kwargs: object) -> None:
        calls.append((command, kwargs))

    monkeypatch.setattr("scripts.release_checks.subprocess.run", run)
    check_test_matrix(release_root, "1.1.2")
    assert [Path(command[1]).name for command, _ in calls] == [
        "build.py", "versioned_test_harness.py",
    ]
    assert calls[1][0][2:] == ["run-tests-all", "--pytest-args", "-q"]
    for _, kwargs in calls:
        assert kwargs["cwd"] == release_root
        assert kwargs["check"] is True
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert "ASTICHI_SKIP_NATIVE_BUILD" not in env
        assert env["ASTICHI_REQUIRE_NATIVE_BUILD"] == "1"
        assert env["ASTICHI_LOWER_ENGINE_MATRIX"] == "1"


def test_gearu_configuration_keeps_cargo_out_of_release_versioning() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "gearu.toml").read_text(encoding="utf-8"))
    assert "rust" not in config
    assert config["python"]["lockfiles"] == ["uv.lock"]
    assert config["release"]["managed_files"] == ["src/astichi/__init__.py"]
    assert not any("sync-version" in command for command in config["release"]["exact_checks"])
    for checks in (config["release"]["checks"], config["release"]["exact_checks"]):
        assert any("test-matrix" in command for command in checks)
