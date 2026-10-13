"""Canonical JSON helpers: one stable serialisation so content hashes are reproducible."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(value: Any) -> str:
    """Serialise ``value`` deterministically (sorted keys, no whitespace, UTF-8 kept)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(value: Any) -> str:
    """sha256 hex digest of the canonical JSON form of ``value``."""
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
