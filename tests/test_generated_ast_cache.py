from __future__ import annotations

from dataclasses import replace

import pytest

import astichi
from astichi.cache import GeneratedAstCache


def _builder(source: str = "answer = 42\n"):
    builder = astichi.build()
    builder.add.Root(astichi.compile(source, file_name="tests/cache_case.py"))
    return builder


def _exec_tree(tree) -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(compile(tree, "<cached-ast>", "exec"), namespace)  # noqa: S102
    return namespace


def test_builder_executable_ast_cache_hit_skips_build_merge(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = GeneratedAstCache(tmp_path)
    builder = _builder()

    cold_tree = builder.to_executable_ast(cache=cache)
    assert _exec_tree(cold_tree)["answer"] == 42

    import astichi.materialize as materialize_module

    def fail_build_merge(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("build_merge should not run on a cache hit")

    monkeypatch.setattr(materialize_module, "build_merge", fail_build_merge)

    warm_tree = builder.to_executable_ast(cache=cache)
    assert _exec_tree(warm_tree)["answer"] == 42


def test_builder_executable_ast_cache_hits_from_disk(tmp_path) -> None:
    cache = GeneratedAstCache(tmp_path)
    builder = _builder()
    key = cache.key_for_builder_graph(builder.graph)
    builder.to_executable_ast(cache=cache)

    disk_cache = GeneratedAstCache(tmp_path)
    cached = disk_cache.load(key)

    assert cached is not None
    assert _exec_tree(cached)["answer"] == 42


def test_builder_executable_ast_cache_dir_surface(tmp_path) -> None:
    tree = _builder().to_executable_ast(cache_dir=tmp_path)

    assert _exec_tree(tree)["answer"] == 42


def test_generated_ast_cache_key_changes_for_semantic_inputs(tmp_path) -> None:
    cache = GeneratedAstCache(tmp_path)
    key = cache.key_for_builder_graph(_builder().graph)
    changed_source = cache.key_for_builder_graph(_builder("answer = 43\n").graph)
    changed_unroll = cache.key_for_builder_graph(_builder().graph, unroll=True)

    shifted = astichi.build()
    shifted.add.Root(
        astichi.compile(
            "answer = 42\n",
            file_name="tests/cache_case_shifted.py",
            line_number=5,
        )
    )
    changed_location = cache.key_for_builder_graph(shifted.graph)

    assert changed_source.digest != key.digest
    assert changed_unroll.digest != key.digest
    assert changed_location.digest != key.digest


def test_generated_ast_cache_manifest_mismatch_misses(tmp_path) -> None:
    cache = GeneratedAstCache(tmp_path)
    builder = _builder()
    key = cache.key_for_builder_graph(builder.graph)
    cache.store(key, builder.to_executable_ast())
    changed_manifest = dict(key.manifest)
    changed_manifest["python"] = dict(changed_manifest["python"])
    changed_manifest["python"]["cache_tag"] = "bad-cache-tag"
    mismatched_key = replace(key, manifest=changed_manifest)

    assert cache.load(mismatched_key) is None


def test_generated_ast_cache_corrupt_payload_misses(tmp_path) -> None:
    cache = GeneratedAstCache(tmp_path)
    key = cache.key_for_builder_graph(_builder().graph)
    cache.cache_dir.mkdir(exist_ok=True)
    cache._path_for_key(key).write_bytes(b"not a pickle")

    assert cache.load(key) is None


def test_generated_ast_cache_hit_returns_independent_tree(tmp_path) -> None:
    cache = GeneratedAstCache(tmp_path)
    builder = _builder()
    builder.to_executable_ast(cache=cache)

    first = builder.to_executable_ast(cache=cache)
    first.body[0].value.value = 0
    assert _exec_tree(first)["answer"] == 0

    second = builder.to_executable_ast(cache=cache)
    assert _exec_tree(second)["answer"] == 42


def test_builder_to_executable_ast_rejects_two_cache_surfaces(tmp_path) -> None:
    builder = _builder()

    with pytest.raises(ValueError, match="either cache or cache_dir"):
        builder.to_executable_ast(cache=GeneratedAstCache(tmp_path), cache_dir=tmp_path)
