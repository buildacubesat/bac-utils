# SPDX-License-Identifier: MIT
"""Data models.

:class:`ResourceDecision` is the trust boundary between the classifier and
the site. The LLM sees untrusted document text, so anything it returns is
treated as untrusted too: text fields are stripped of HTML and control
characters before they can reach markdown (MkDocs renders raw HTML), title
text is made safe inside ``[title](url)``, block ids must be kebab-case, and
paths must be relative ``.md`` files without ``..`` segments. Validation also
runs on assignment, so interactive edits pass through the same rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .utils import is_valid_block_id

# Elements whose body is code, not text: removed with their content.
_HTML_DANGEROUS_ELEMENT_RE = re.compile(r"<(script|style|iframe|object|embed)\b[^>]*>.*?</\1\s*>", re.I | re.S)
# Anything that looks like a tag: `<b>`, `</b>`, `<img src=x>`, `<!-- -->`, `<?xml ?>`.
_HTML_TAG_RE = re.compile(r"</?[A-Za-z!?][^>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(value: str, *, link_safe: bool = False) -> str:
    """Plain, single-line text: no HTML, no control characters, collapsed whitespace.

    Script-like elements go with their body; other tags are removed and their
    text kept; stray angle brackets are dropped so nothing can be reassembled
    into markup downstream. With ``link_safe`` the result can sit inside
    ``**[title](url)**``: square brackets become parentheses, backticks
    become apostrophes, and bold markers are removed.
    """
    value = _HTML_DANGEROUS_ELEMENT_RE.sub("", value)
    value = _HTML_TAG_RE.sub("", value)
    value = value.replace("<", "").replace(">", "")
    value = _CONTROL_RE.sub(" ", value)
    value = " ".join(value.split())
    if link_safe:
        value = value.replace("[", "(").replace("]", ")").replace("`", "'").replace("**", "")
    return value


def check_rel_md(value: str) -> str:
    """Shape check for a repo-relative markdown path. Existence is checked against the repo later."""
    if _CONTROL_RE.search(value) or "\\" in value:
        raise ValueError("path contains control characters or backslashes")
    p = PurePosixPath(value.strip())
    if p.is_absolute() or Path(value).is_absolute():
        raise ValueError(f"absolute paths are not allowed: {value}")
    if ".." in p.parts:
        raise ValueError(f"'..' is not allowed in paths: {value}")
    if p.suffix.lower() != ".md":
        raise ValueError(f"expected a .md path, got: {value}")
    return p.as_posix()


@dataclass(slots=True)
class SourceItem:
    original: str
    kind: Literal["local_file", "url_document", "external_url"]
    staged_path: Path | None = None
    source_url: str | None = None
    hint: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ExtractedDocument:
    source: SourceItem
    title_hint: str | None
    content_excerpt: str
    sha256: str
    extension: str
    size_bytes: int
    metadata: dict = field(default_factory=dict)

    @property
    def hint(self) -> str | None:
        return self.source.hint


_BLOCK_ID_FIELDS = ("target_block_id", "suggested_block_id")
_PATH_FIELDS = ("target_markdown_file", "suggested_parent_file", "suggested_path")


class ResourceDecision(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    title: str = Field(..., min_length=3, max_length=180)
    description: str = Field(..., min_length=3, max_length=180)
    publisher: str | None = Field(default=None, max_length=120)
    author: str | None = Field(default=None, max_length=160)
    year: int | None = Field(default=None, ge=1900, le=2100)
    resource_type: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=12)
    suggested_filename: str = Field(..., min_length=3, max_length=180)
    placement_type: Literal["existing_block", "new_block_requested", "new_page_requested"]
    target_block_id: str | None = None
    target_markdown_file: str | None = None
    suggested_parent_file: str | None = None
    suggested_heading: str | None = None
    suggested_parent_heading: str | None = None
    suggested_block_id: str | None = None
    suggested_path: str | None = None
    suggested_nav_title: str | None = None
    reason: str = Field(..., min_length=3, max_length=500)
    confidence: float = Field(..., ge=0, le=1)

    # Cleaning runs in "before" validators so that it happens on construction
    # and on assignment alike, and before the length constraints are checked.

    @field_validator("title", mode="before")
    @classmethod
    def _title_link_safe(cls, value):
        return clean_text(value, link_safe=True) if isinstance(value, str) else value

    @field_validator("description", "reason", mode="before")
    @classmethod
    def _plain_required(cls, value):
        return clean_text(value) if isinstance(value, str) else value

    @field_validator(
        "publisher",
        "author",
        "resource_type",
        "suggested_heading",
        "suggested_parent_heading",
        "suggested_nav_title",
        mode="before",
    )
    @classmethod
    def _plain_optional(cls, value):
        if isinstance(value, str):
            return clean_text(value) or None
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_plain(cls, value):
        if not isinstance(value, list):
            return value
        seen: set[str] = set()
        tags: list[str] = []
        for tag in value:
            if not isinstance(tag, str):
                continue
            cleaned = clean_text(tag, link_safe=True)[:40]
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                tags.append(cleaned)
        return tags

    @field_validator(*_BLOCK_ID_FIELDS, *_PATH_FIELDS, mode="before")
    @classmethod
    def _strip_identifiers(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("target_block_id", "suggested_block_id", mode="after")
    @classmethod
    def _block_id_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_block_id(value):
            raise ValueError(f"block id must be lowercase kebab-case, got: {value!r}")
        return value

    @field_validator("target_markdown_file", "suggested_parent_file", "suggested_path", mode="after")
    @classmethod
    def _path_shape(cls, value: str | None) -> str | None:
        return check_rel_md(value) if value is not None else None


class ResourceRecord(BaseModel):
    """One indexed resource.

    ``url`` is the identity key; ``block_ids`` lists every block the resource
    appears in (cross-listing is allowed and rendered identically in each).
    ``sha256`` is only known for resources that passed through ingest (file
    hash, or URL hash for external links); records backfilled by
    ``sync-blocks`` have no hash. ``added_by`` records which path created the
    entry so unenriched sync records can be found later.
    """

    id: str
    title: str
    description: str = ""
    file_type: str
    url: str
    source: str
    block_ids: list[str] = Field(default_factory=list, min_length=1)
    publisher: str | None = None
    author: str | None = None
    year: int | None = None
    resource_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    sha256: str | None = None
    added: str
    added_by: Literal["ingest", "sync"] = "ingest"

    @model_validator(mode="before")
    @classmethod
    def _migrate_block_id(cls, data):
        """Accept the pre-0.3.1 single ``block_id`` field."""
        if isinstance(data, dict) and "block_id" in data and "block_ids" not in data:
            data = {**data, "block_ids": [data.pop("block_id")]}
        return data


class BlockTarget(BaseModel):
    """Compact block description handed to the classifier."""

    block_id: str
    file: str
    heading_context: list[str]
    description: str
