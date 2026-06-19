"""Resolve an evidence/snapshot filename to bytes, safely (no path traversal)."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}


def safe_name(filename: str) -> Optional[str]:
    """Reject anything but a bare filename (no separators, no ..)."""
    if not filename:
        return None
    base = os.path.basename(filename)
    if base != filename or base in ("", ".", ".."):
        return None
    return base


def resolve(filename: str, image_dirs: List[str]) -> Optional[Tuple[bytes, str]]:
    """Return (bytes, content_type) from the first dir that has the file, else None."""
    base = safe_name(filename)
    if not base:
        return None
    ctype = _CONTENT_TYPES.get(os.path.splitext(base)[1].lower(), "application/octet-stream")
    for d in image_dirs:
        path = os.path.join(d, base)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                return fh.read(), ctype
    return None
