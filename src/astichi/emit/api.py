"""Source emission for Astichi V1."""

from __future__ import annotations

import ast
import base64
import pickle
import zlib

from astichi.diagnostics import format_astichi_error

PROVENANCE_PREFIX = "# astichi-provenance: "


def emit_source(tree: ast.Module, *, provenance: bool = True) -> str:
    """Emit valid Python source text from an AST module."""
    text = ast.unparse(tree)
    if not text.endswith("\n"):
        text += "\n"
    if provenance:
        payload = encode_provenance(tree)
        text += PROVENANCE_PREFIX + payload + "\n"
    return text


def encode_provenance(tree: ast.Module) -> str:
    """Pickle, compress, and base64-encode the AST for provenance."""
    raw = pickle.dumps(tree, protocol=pickle.HIGHEST_PROTOCOL)
    compressed = zlib.compress(raw, level=9)
    return base64.b64encode(compressed).decode("ascii")


def decode_provenance(payload: str) -> ast.Module:
    """Reverse the provenance encoding: base64-decode, decompress, unpickle."""
    compressed = base64.b64decode(payload.encode("ascii"))
    raw = zlib.decompress(compressed)
    tree = pickle.loads(raw)  # noqa: S301
    if not isinstance(tree, ast.Module):
        raise TypeError(f"provenance payload is not an ast.Module: {type(tree)}")
    return tree


def extract_provenance(source: str) -> ast.Module | None:
    """Extract and decode provenance from emitted source text, if present."""
    for line in source.splitlines():
        if line.startswith(PROVENANCE_PREFIX):
            payload = line[len(PROVENANCE_PREFIX) :].strip()
            return decode_provenance(payload)
    return None


class RoundTripError(Exception):
    """Raised when emitted source does not match its provenance AST."""


def verify_round_trip(source: str) -> None:
    """Verify emitted source re-parses to match its embedded provenance."""
    provenance_tree = extract_provenance(source)
    if provenance_tree is None:
        raise RoundTripError(
            format_astichi_error(
                "emit",
                "source has no embedded provenance comment",
                provenance="append `# astichi-provenance:` with `emit(provenance=True)`",
                hint="use `from astichi.emit import extract_provenance` to inspect the trailer",
            )
        )

    source_lines = [
        line
        for line in source.splitlines()
        if not line.startswith(PROVENANCE_PREFIX)
    ]
    clean_source = "\n".join(source_lines) + "\n"
    reparsed = ast.parse(clean_source)

    expected = ast.dump(provenance_tree)
    actual = ast.dump(reparsed)
    if expected != actual:
        raise RoundTripError(
            format_astichi_error(
                "emit",
                "round-trip mismatch between emitted source and embedded provenance AST",
                provenance="compare `extract_provenance(source)` with `ast.parse` of the emitted body",
                hint=f"expected dump prefix: {expected[:200]!r}; actual: {actual[:200]!r}",
            )
        )
