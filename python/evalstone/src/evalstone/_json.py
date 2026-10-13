"""Canonical JSON helpers: one stable serialisation so content hashes are reproducible.

Only JSON-native values plus a few explicitly handled types (sets, tuples,
bytes, dates, enums, pydantic models, dataclasses) are accepted. Anything else
raises ``TypeError`` instead of being stringified — ``str(obj)`` would bake a
memory address or a hash-randomised set order into a content hash.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import enum
import hashlib
import json
from typing import Any


def _encode(value: Any) -> Any:
    """Convert the supported non-JSON types to a deterministic JSON-native form."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise TypeError("dict keys must be strings to hash")
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, set | frozenset):
        return sorted((_encode(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, tuple):
        return [_encode(v) for v in value]
    if isinstance(value, bytes | bytearray):
        return {"__bytes__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if hasattr(value, "model_dump") and callable(value.model_dump):  # pydantic
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    raise TypeError(f"not JSON-serialisable for hashing/text: {type(value).__name__}")


def dumps(value: Any, **kwargs: Any) -> str:
    """``json.dumps`` with the explicit encoder above (never ``default=str``)."""
    return json.dumps(_encode(value), ensure_ascii=False, **kwargs)


def canonical(value: Any) -> str:
    """Serialise ``value`` deterministically (sorted keys, no whitespace, UTF-8 kept)."""
    return dumps(_encode(value), sort_keys=True, separators=(",", ":"))


def sha256(value: Any) -> str:
    """sha256 hex digest of the canonical JSON form of ``value``."""
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
