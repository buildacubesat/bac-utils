# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from .blocks import render_entry
from .models import ResourceRecord
from .utils import file_type_label, normalize_url, short_hash


class ResourceIndex:
    """``data/resources.yml`` in memory, keyed by normalised URL.

    The YAML file is a legacy exception to the project's no-YAML rule: it is
    an existing data file and is kept as-is.
    """

    def __init__(self, path: Path):
        self.path = path
        self._records: dict[str, ResourceRecord] = {}
        self.load()

    # -- persistence -------------------------------------------------------

    def load(self) -> None:
        self._records = {}
        if not self.path.exists():
            return
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        for item in data.get("resources", []):
            record = ResourceRecord.model_validate(item)
            self._records[normalize_url(record.url)] = record

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "resources": [
                r.model_dump(exclude_none=True) for r in sorted(self._records.values(), key=lambda r: r.title.lower())
            ]
        }
        self.path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    # -- queries -----------------------------------------------------------

    @property
    def records(self) -> list[ResourceRecord]:
        return list(self._records.values())

    def __len__(self) -> int:
        return len(self._records)

    def get(self, url: str) -> ResourceRecord | None:
        return self._records.get(normalize_url(url))

    def find_by_sha(self, sha256: str) -> ResourceRecord | None:
        for r in self._records.values():
            if r.sha256 == sha256:
                return r
        return None

    def by_block(self) -> dict[str, list[ResourceRecord]]:
        grouped: dict[str, list[ResourceRecord]] = {}
        for r in self._records.values():
            for bid in r.block_ids:
                grouped.setdefault(bid, []).append(r)
        return grouped

    def rendered_lines_by_block(self) -> dict[str, list[str]]:
        return {
            block_id: [render_entry(r.title, r.url, r.file_type, r.description) for r in records]
            for block_id, records in self.by_block().items()
        }

    # -- mutation ----------------------------------------------------------

    def upsert(self, record: ResourceRecord) -> None:
        self._records[normalize_url(record.url)] = record

    def remove(self, url: str) -> bool:
        return self._records.pop(normalize_url(url), None) is not None


def record_id(url: str) -> str:
    return short_hash(normalize_url(url), 10)


def make_record(
    *,
    title: str,
    description: str,
    file_type: str,
    url: str,
    source: str,
    block_ids: list[str],
    publisher: str | None = None,
    author: str | None = None,
    year: int | None = None,
    resource_type: str | None = None,
    tags: list[str] | None = None,
    sha256: str | None = None,
    added_by: str = "ingest",
) -> ResourceRecord:
    return ResourceRecord(
        id=record_id(url),
        title=title,
        description=description,
        file_type=resource_file_type_label(file_type),
        url=url,
        source=source,
        block_ids=list(block_ids),
        publisher=publisher,
        author=author,
        year=year,
        resource_type=resource_type,
        tags=tags or [],
        sha256=sha256,
        added=date.today().isoformat(),
        added_by=added_by,  # type: ignore[arg-type]
    )


def resource_file_type_label(value: str) -> str:
    """Accept an extension (``.pdf``), a kind (``link``) or an existing label (``PDF``)."""
    raw = (value or "").strip()
    lowered = raw.lower()
    if lowered in {"", ".url", "url", "link", "external_url", "external-link"}:
        return "Link"
    if lowered.startswith("."):
        return file_type_label(lowered)
    return raw
