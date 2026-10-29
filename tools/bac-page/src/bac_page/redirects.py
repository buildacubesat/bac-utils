# SPDX-License-Identifier: MIT
"""The redirects: one folder per slug in the Pages repository, each holding an ``index.html``.

The file is a meta refresh plus a script fallback and a canonical link, the shape GitHub
Pages has served since the first slug; ``parse_target`` reads the target back out of it.
A renamed slug keeps its folder as an alias: its file redirects to the new short URL and
carries ``<meta name="bac-page" content="renamed <YYYY-MM-DD> to /<new>">``, which
``parse_renamed`` reads, so the folders alone tell an alias from a live slug.
"""

from __future__ import annotations

import random
import re
import string
from pathlib import Path
from typing import NamedTuple

from bac_common.errors import BacError, UsageError

DOMAIN = "bac.page"
UID_LENGTH = 8
SLUG_MAX = 24
SLUG_PATTERN = re.compile(rf"^[a-zA-Z0-9-]{{1,{SLUG_MAX}}}$")
TARGET_PATTERN = re.compile(r"^https?://\S+$")
# folders in the repository that are not redirects
SKIP_DIRS = {"cli"}
RENAMED_PATTERN = re.compile(
    rf'<meta name="bac-page" content="renamed (\d{{4}}-\d{{2}}-\d{{2}}) to /([a-zA-Z0-9-]{{1,{SLUG_MAX}}})">'
)

__all__ = [
    "DOMAIN",
    "SLUG_MAX",
    "Redirect",
    "create_redirect",
    "generate_uid",
    "list_redirects",
    "parse_renamed",
    "parse_target",
    "redirect_html",
    "short_url",
    "slug_exists",
    "validate_slug",
    "validate_target",
    "write_alias",
]


class Redirect(NamedTuple):
    """One folder of the Pages repository; ``renamed_to`` and ``renamed_on`` are set for an alias."""

    slug: str
    target: str
    renamed_to: str | None = None
    renamed_on: str | None = None

    @property
    def is_alias(self) -> bool:
        return self.renamed_to is not None


def generate_uid() -> str:
    """A random slug: eight letters and digits."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=UID_LENGTH))


def short_url(slug: str) -> str:
    return f"https://{DOMAIN}/{slug}"


def redirect_html(target: str, renamed: tuple[str, str] | None = None) -> str:
    """The redirect page; ``renamed`` = ``(date, new slug)`` adds the alias marker."""
    marker = f'  <meta name="bac-page" content="renamed {renamed[0]} to /{renamed[1]}">\n' if renamed else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
{marker}  <meta http-equiv="refresh" content="0; url={target}">
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
    """Any folder of that name takes the slug, with or without a redirect in it (``git mv`` would nest into it)."""
    return (repo / slug).exists()


def validate_slug(repo: Path, slug: str) -> None:
    """A malformed slug is a usage error (2); a taken one – live or an alias – a plain error (1)."""
    if not SLUG_PATTERN.match(slug):
        raise UsageError(f"Invalid slug: {slug!r}", f"Use 1–{SLUG_MAX} characters: letters, digits and hyphens.")
    if slug_exists(repo, slug):
        index = repo / slug / "index.html"
        renamed = parse_renamed(index) if index.is_file() else None
        if renamed:
            raise BacError(
                f"/{slug} is a renamed slug (now /{renamed[1]}).",
                "Links and QR codes made with it still use it – pick another slug.",
            )
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


def write_alias(repo: Path, slug: str, new_slug: str, date: str) -> Path:
    """Turn ``<repo>/<slug>`` into an alias of ``new_slug``, renamed on ``date`` (YYYY-MM-DD)."""
    folder = repo / slug
    folder.mkdir(exist_ok=True)
    html = redirect_html(short_url(new_slug), renamed=(date, new_slug))
    (folder / "index.html").write_text(html, encoding="utf-8")
    return folder


def parse_target(index_html: Path) -> str | None:
    match = re.search(r'content="0; url=([^"]+)"', index_html.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def parse_renamed(index_html: Path) -> tuple[str, str] | None:
    """``(date, new slug)`` when the file is an alias left by a rename."""
    match = RENAMED_PATTERN.search(index_html.read_text(encoding="utf-8"))
    return (match.group(1), match.group(2)) if match else None


def list_redirects(repo: Path) -> list[Redirect]:
    """Every redirect, live and alias, sorted by slug without regard to case."""
    entries: list[Redirect] = []
    for folder in repo.iterdir():
        if not folder.is_dir() or folder.name.startswith(".") or folder.name in SKIP_DIRS:
            continue
        index = folder / "index.html"
        if index.exists():
            target = parse_target(index)
            if target:
                renamed = parse_renamed(index)
                if renamed:
                    entries.append(Redirect(folder.name, target, renamed_to=renamed[1], renamed_on=renamed[0]))
                else:
                    entries.append(Redirect(folder.name, target))
    return sorted(entries, key=lambda entry: (entry[0].lower(), entry[0]))
