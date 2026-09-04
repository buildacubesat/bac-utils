# SPDX-License-Identifier: MIT
"""Small helpers several tools need: hashing, slugs, safe file names."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

__all__ = [
    "KEBAB_RE",
    "is_kebab",
    "sha256_file",
    "short_hash",
    "slugify",
    "safe_filename",
]

# Lowercase kebab-case: no leading, trailing or double hyphens.
KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_TRANSLITERATE = str.maketrans({"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ł": "l"})


def is_kebab(value: str) -> bool:
    """True for identifiers like ``solar-cell-datasheets``."""
    return bool(KEBAB_RE.match(value))


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file, streamed in 1 MiB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def short_hash(value: str, length: int = 8) -> str:
    """First ``length`` hex characters of the SHA-256 of a string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def slugify(text: str, *, separator: str = "-", max_length: int | None = None) -> str:
    """ASCII, lowercase, ``separator``-joined words. ``ä`` becomes ``a``, ``ß`` becomes ``ss``.

    Truncation at ``max_length`` happens on a word boundary where possible.
    """
    text = text.translate(_TRANSLITERATE)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    words = [w for w in re.split(r"[^A-Za-z0-9]+", text) if w]
    slug = separator.join(w.lower() for w in words)
    if max_length is not None and len(slug) > max_length:
        cut = slug[:max_length]
        if separator and separator in cut:
            cut = cut.rsplit(separator, 1)[0] or cut
        slug = cut.rstrip(separator)
    return slug


def safe_filename(name: str, fallback_ext: str = "", *, max_stem: int = 140) -> str:
    """A slugified file name that keeps a lowercase extension.

    ``report Final (v2).PDF`` becomes ``report-final-v2.pdf``. A name with
    no extension gets ``fallback_ext``. An empty stem becomes ``file``.
    """
    p = Path(name)
    ext = p.suffix.lower() if p.suffix else fallback_ext.lower()
    stem = p.stem if p.suffix else name
    slug = slugify(stem, max_length=max_stem) or "file"
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return f"{slug}{ext}"
