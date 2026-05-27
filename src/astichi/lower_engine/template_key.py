"""Stable template identity from canonical registration source text."""

from __future__ import annotations

import hashlib


def template_key_from_source(source: str) -> str:
    """Return ``template:<16 hex>`` from SHA-256 of UTF-8 ``source`` bytes."""
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return f"template:{digest}"
