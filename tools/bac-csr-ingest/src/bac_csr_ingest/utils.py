# SPDX-License-Identifier: MIT
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from slugify import slugify

from bac_common.utils import KEBAB_RE, is_kebab, sha256_file, short_hash

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "BLOCK_ID_RE",
    "is_url",
    "normalize_url",
    "sha256_file",
    "short_hash",
    "safe_filename",
    "is_valid_block_id",
    "file_type_label",
    "file_type_from_url",
    "strip_markdown_noise",
]

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
    ".html", ".htm", ".md", ".txt", ".csv", ".rtf", ".odt", ".ods", ".odp",
}  # fmt: skip

# Canonical block ids: lowercase kebab-case, no leading/trailing/double hyphens.
BLOCK_ID_RE = KEBAB_RE


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_url(value: str) -> str:
    """Canonical form used as the identity key for resources.

    Lowercases scheme and host, strips surrounding whitespace, and drops a
    trailing slash on a bare host. Path, query and fragment are preserved
    verbatim because they can be significant (anchors, version query strings).
    """
    value = value.strip()
    parsed = urlparse(value)
    if not parsed.scheme:
        return value
    path = parsed.path
    if path == "/" and not parsed.query and not parsed.fragment:
        path = ""
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.params, parsed.query, parsed.fragment)
    )


def safe_filename(name: str, fallback_ext: str) -> str:
    """Slugified file name with a lowercase extension.

    Uses python-slugify (not :func:`bac_common.utils.slugify`) on purpose:
    blob names already published under the previous version must keep
    slugifying identically, or re-ingest would stop matching them.
    """
    path = Path(name)
    ext = path.suffix.lower() or fallback_ext.lower()
    stem = path.stem if path.suffix else name
    stem = slugify(stem, max_length=140, lowercase=True)
    if not stem:
        stem = "resource"
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{stem}{ext}"


def is_valid_block_id(block_id: str) -> bool:
    return is_kebab(block_id)


def file_type_label(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    return ext.upper() if ext else "FILE"


def file_type_from_url(url: str) -> str:
    """Best-effort `PDF`/`XLSX`/… label from a URL path, else `Link`."""
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix and suffix in SUPPORTED_EXTENSIONS and suffix not in {".html", ".htm"}:
        return file_type_label(suffix)
    return "Link"


def strip_markdown_noise(text: str, limit: int = 16000) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]
