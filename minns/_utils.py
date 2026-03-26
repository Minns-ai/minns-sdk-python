"""Internal utilities shared across the SDK."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any


def to_u128(id_val: str | int) -> str:
    """Convert a UUID or hex string to a numeric string representing a u128."""
    if isinstance(id_val, int):
        return str(id_val)
    if "-" not in id_val:
        try:
            int(id_val)
            return id_val
        except ValueError:
            pass
    try:
        hex_str = id_val.replace("-", "")
        return str(int(hex_str, 16))
    except (ValueError, OverflowError):
        return "0"


def get_nanoseconds() -> str:
    """Return current time as a nanosecond-precision string."""
    return str(int(time.time() * 1_000_000_000))


def generate_u128_id() -> str:
    """Generate a random u128 ID from a UUID."""
    return to_u128(str(uuid.uuid4()))


def safe_stringify(obj: Any) -> str:
    """JSON-serialize with circular-reference protection and BigInt handling.

    Mirrors the TypeScript ``safeStringify`` — strips ``__proto__`` /
    ``constructor`` keys and replaces circular refs with ``"[Circular]"``.
    """
    seen: set[int] = set()

    def _default(o: Any) -> Any:
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    def _filter(obj: Any) -> Any:
        if isinstance(obj, dict):
            obj_id = id(obj)
            if obj_id in seen:
                return "[Circular]"
            seen.add(obj_id)
            return {
                k: _filter(v)
                for k, v in obj.items()
                if k not in ("__proto__", "constructor")
            }
        if isinstance(obj, (list, tuple)):
            return [_filter(v) for v in obj]
        return obj

    return json.dumps(_filter(obj), default=_default, separators=(",", ":"))


def strip_none(d: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *d* with ``None``-valued keys removed."""
    return {k: v for k, v in d.items() if v is not None}
