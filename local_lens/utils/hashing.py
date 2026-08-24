"""Stable content hashing.

The original app used Python's built-in `hash()` on raw image bytes as a
cache/session-state key. `hash()` is salted per-process (PYTHONHASHSEED) for
str/bytes-derived objects in some configurations and is not guaranteed
stable across runs, which makes it unsafe as a durable cache key. MD5 is
used here purely as a fast, stable fingerprint -- not for any security
purpose.
"""

from __future__ import annotations

import hashlib

# First N bytes is enough to distinguish practically-encountered images
# (different screenshots virtually never share a long byte prefix) while
# keeping hashing fast for very large images.
_HASH_PREFIX_BYTES = 200_000


def hash_image_bytes(data: bytes) -> str:
    """Return a stable hex digest fingerprinting `data`."""
    prefix = data[:_HASH_PREFIX_BYTES]
    return hashlib.md5(prefix).hexdigest()
