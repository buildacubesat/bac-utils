# SPDX-License-Identifier: MIT
"""The redirects: one folder per slug in the Pages repository, each holding an ``index.html``.

The file is a meta refresh plus a script fallback and a canonical link, the shape GitHub
Pages has served since the first slug; ``parse_target`` reads the target back out of it.
"""

from __future__ import annotations

import random
import re
import string
from pathlib import Path

from bac_common.errors import BacError, UsageError

DOMAIN = "bac.page"
UID_LENGTH = 8
SLUG_MAX = 24
SLUG_PATTERN = re.compile(rf"^[a-zA-Z0-9-]{{1,{SLUG_MAX}}}$")
TARGET_PATTERN = re.compile(r"^https?://\S+$")
# folders in the repository that are not redirects
SKIP_DIRS = {"cli"}

__all__ = [
    "DOMAIN",
    "SLUG_MAX",
    "create_redirect",
    "generate_uid",
    "list_redirects",
    "parse_target",
    "redirect_html",
    "short_url",
    "slug_exists",
    "validate_slug",
    "validate_target",
]


def generate_uid() -> str:
    """A random slug: eight letters and digits."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=UID_LENGTH))


def short_url(slug: str) -> str:
    return f"https://{DOMAIN}/{slug}"


def redirect_html(target: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={target}">
  <link rel="canonical" href="{target}">
  <title>Redirecting…</title>
</head>
<body>
  <p>Redirecting to <a href="{target}">{target}</a></p>
  <script>window.location.replace({target!r});</script>
</body>
</html>
"""


def slug_exists(repo: Path, slug: str) -> bool:
    return (repo / slug / "index.html").exists()


def validate_slug(repo: Path, slug: str) -> None:
    """A malformed slug is a usage error (2); a taken one a plain error (1)."""
    if not SLUG_PATTERN.match(slug):
        raise UsageError(f"Invalid slug: {slug!r}", f"Use 1–{SLUG_MAX} characters: letters, digits and hyphens.")
    if slug_exists(repo, slug):
        raise BacError(f"/{slug} already exists.", "Run `bac-page list` to see the current redirects.")


def validate_target(target: str) -> None:
    if not TARGET_PATTERN.match(target):
        raise UsageError(f"Target must be an http(s) URL: {target!r}")


def create_redirect(repo: Path, slug: str, target: str) -> Path:
    """Write ``<repo>/<slug>/index.html`` and return the folder."""
    folder = repo / slug
    folder.mkdir(exist_ok=True)
    (folder / "index.html").write_text(redirect_html(target), encoding="utf-8")
    return folder


def parse_target(index_html: Path) -> str | None:
    match = re.search(r'content="0; url=([^"]+)"', index_html.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def list_redirects(repo: Path) -> list[tuple[str, str]]:
    """``(slug, target)`` pairs, sorted by slug without regard to case."""
    entries: list[tuple[str, str]] = []
    for folder in repo.iterdir():
        if not folder.is_dir() or folder.name.startswith(".") or folder.name in SKIP_DIRS:
            continue
        index = folder / "index.html"
        if index.exists():
            target = parse_target(index)
            if target:
                entries.append((folder.name, target))
    return sorted(entries, key=lambda entry: (entry[0].lower(), entry[0]))
