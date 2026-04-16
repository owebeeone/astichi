"""Source emission and provenance handling for Astichi."""

from astichi.emit.api import (
    RoundTripError,
    decode_provenance,
    emit_source,
    encode_provenance,
    extract_provenance,
    verify_round_trip,
)

__all__ = [
    "RoundTripError",
    "decode_provenance",
    "emit_source",
    "encode_provenance",
    "extract_provenance",
    "verify_round_trip",
]
