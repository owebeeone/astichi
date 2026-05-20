"""Opt-in generated AST cache for trusted local build artifacts."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pickle
import platform
import sys
import tempfile
from typing import Any

from astichi import __version__
from astichi.ast_provenance import astichi_source_file
from astichi.builder.graph import (
    AdditiveEdge,
    AssignBinding,
    BuilderGraph,
    IdentifierBinding,
    InstanceRecord,
)
from astichi.model.basic import BasicComposable

_CACHE_FORMAT_VERSION = 1
_AST_CACHE_SCHEMA_VERSION = 1
_CACHE_FILE_SUFFIX = ".astichi-ast.pickle"


@dataclass(frozen=True)
class GeneratedAstCacheKey:
    """Checked-hash cache key for a generated executable AST."""

    digest: str
    manifest: dict[str, Any]


class GeneratedAstCache:
    """Trusted local cache for executable AST snapshots.

    Cache payloads are pickled ASTs and must be treated like generated code:
    only load entries from cache directories controlled by the current user or
    build system.
    """

    def __init__(self, cache_dir: str | os.PathLike[str]) -> None:
        self.cache_dir = Path(cache_dir)
        self._memory_payloads: dict[str, bytes] = {}

    def key_for_builder_graph(
        self,
        graph: BuilderGraph,
        *,
        unroll: bool | str = "auto",
    ) -> GeneratedAstCacheKey:
        return build_generated_ast_cache_key(graph, unroll=unroll)

    def load(self, key: GeneratedAstCacheKey) -> ast.Module | None:
        payload = self._memory_payloads.get(key.digest)
        if payload is None:
            path = self._path_for_key(key)
            try:
                payload = path.read_bytes()
            except OSError:
                return None
        entry = self._decode_payload(payload)
        if entry is None:
            return None
        if entry.get("digest") != key.digest:
            return None
        if entry.get("manifest") != key.manifest:
            return None
        tree = entry.get("tree")
        if not isinstance(tree, ast.Module):
            return None
        return tree

    def store(self, key: GeneratedAstCacheKey, tree: ast.Module) -> None:
        owned_tree = copy.deepcopy(tree)
        ast.fix_missing_locations(owned_tree)
        payload = pickle.dumps(
            {
                "digest": key.digest,
                "manifest": key.manifest,
                "tree": owned_tree,
            },
            protocol=pickle.HIGHEST_PROTOCOL,
        )
        self._memory_payloads[key.digest] = payload
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        final_path = self._path_for_key(key)
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=self.cache_dir,
            prefix=f".{key.digest}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            try:
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
        os.replace(temp_path, final_path)

    def _path_for_key(self, key: GeneratedAstCacheKey) -> Path:
        return self.cache_dir / f"{key.digest}{_CACHE_FILE_SUFFIX}"

    def _decode_payload(self, payload: bytes) -> dict[str, Any] | None:
        try:
            entry = pickle.loads(payload)  # noqa: S301
        except Exception:
            return None
        return entry if isinstance(entry, dict) else None


def build_generated_ast_cache_key(
    graph: BuilderGraph,
    *,
    unroll: bool | str = "auto",
) -> GeneratedAstCacheKey:
    if unroll not in (True, False, "auto"):
        raise ValueError(f"unroll must be True, False, or 'auto'; got {unroll!r}")
    manifest = _builder_graph_manifest(graph, unroll=unroll)
    digest = _manifest_digest(manifest)
    return GeneratedAstCacheKey(digest=digest, manifest=manifest)


def _manifest_digest(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _builder_graph_manifest(
    graph: BuilderGraph,
    *,
    unroll: bool | str,
) -> dict[str, Any]:
    return {
        "format_version": _CACHE_FORMAT_VERSION,
        "ast_schema_version": _AST_CACHE_SCHEMA_VERSION,
        "astichi": {
            "version": __version__,
        },
        "python": {
            "implementation": platform.python_implementation(),
            "cache_tag": sys.implementation.cache_tag,
            "magic_number": importlib.util.MAGIC_NUMBER.hex(),
            "major_minor": [sys.version_info.major, sys.version_info.minor],
        },
        "policy": {
            "output": "executable_ast",
            "comment_policy": "executable",
            "provenance": False,
            "unroll": unroll,
        },
        "graph": {
            "instances": [
                _instance_manifest(record) for record in graph.instances
            ],
            "edges": [_edge_manifest(edge) for edge in graph.edges],
            "assigns": [
                _assign_manifest(binding) for binding in graph.assigns
            ],
            "identifier_bindings": [
                _identifier_binding_manifest(binding)
                for binding in graph.identifier_bindings
            ],
        },
    }


def _instance_manifest(record: InstanceRecord) -> dict[str, Any]:
    if not isinstance(record.composable, BasicComposable):
        raise TypeError(
            f"instance {record.name} must be a BasicComposable for AST caching"
        )
    return {
        "name": record.name,
        "placement": type(record.placement).__qualname__,
        "composable": _composable_manifest(record.composable),
    }


def _composable_manifest(composable: BasicComposable) -> dict[str, Any]:
    return {
        "origin": {
            "file_name": composable.origin.file_name,
            "line_number": composable.origin.line_number,
            "offset": composable.origin.offset,
        },
        "tree": ast.dump(composable.tree, include_attributes=True),
        "astichi_source_files": _astichi_source_file_manifest(composable.tree),
        "bound_externals": sorted(composable.bound_externals),
        "arg_bindings": list(composable.arg_bindings),
        "keep_names": sorted(composable.keep_names),
    }


def _astichi_source_file_manifest(tree: ast.AST) -> list[list[int | str]]:
    result: list[list[int | str]] = []
    for index, node in enumerate(ast.walk(tree)):
        source_file = astichi_source_file(node)
        if source_file is not None:
            result.append([index, source_file])
    return result


def _edge_manifest(edge: AdditiveEdge) -> dict[str, Any]:
    return {
        "target": {
            "root_instance": edge.target.root_instance,
            "target_name": edge.target.target_name,
            "ref_path": list(edge.target.ref_path),
            "path": list(edge.target.path),
        },
        "source_instance": edge.source_instance,
        "order": edge.order,
        "overlay": {
            "arg_names": list(edge.overlay.arg_names),
            "keep_names": sorted(edge.overlay.keep_names),
            "bind_values": [
                [name, _external_value_manifest(value)]
                for name, value in edge.overlay.bind_values
            ],
        },
    }


def _assign_manifest(binding: AssignBinding) -> dict[str, Any]:
    return {
        "source_instance": binding.source_instance,
        "inner_name": binding.inner_name,
        "target_instance": binding.target_instance,
        "outer_name": binding.outer_name,
        "source_ref_path": list(binding.source_ref_path),
        "target_ref_path": list(binding.target_ref_path),
    }


def _identifier_binding_manifest(binding: IdentifierBinding) -> dict[str, Any]:
    return {
        "source_instance": binding.source_instance,
        "inner_name": binding.inner_name,
        "target_instance": binding.target_instance,
        "outer_name": binding.outer_name,
        "source_ref_path": list(binding.source_ref_path),
        "target_ref_path": list(binding.target_ref_path),
    }


def _external_value_manifest(value: object) -> Any:
    if value is None:
        return {"type": "none"}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": repr(value)}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    if isinstance(value, tuple):
        return {
            "type": "tuple",
            "items": [_external_value_manifest(item) for item in value],
        }
    if isinstance(value, list):
        return {
            "type": "list",
            "items": [_external_value_manifest(item) for item in value],
        }
    if isinstance(value, dict):
        return {
            "type": "dict",
            "items": [
                [
                    _external_value_manifest(key),
                    _external_value_manifest(item),
                ]
                for key, item in value.items()
            ],
        }
    raise TypeError(
        f"unsupported external binding value in cache key: {type(value).__name__}"
    )
