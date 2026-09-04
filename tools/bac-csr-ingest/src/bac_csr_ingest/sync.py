# SPDX-License-Identifier: MIT
"""Reconcile ``resources.yml`` with the resource blocks on the site.

Rules:

* Markdown blocks are the source of truth for *which* URL lives in *which*
  block(s), and for the visible title, type badge and description. A URL may
  be cross-listed in several blocks; it must then read identically in each.
* The index is the source of truth for everything else (publisher, author,
  year, resource type, tags, hash, provenance).
* Sync never writes markdown. It only adds, moves and updates index records.
* Sync never deletes. Index records whose URL no longer appears in any block
  are reported as orphans; removing them is an explicit ``--prune``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .blocks import Block, Entry, MarkerProblem, ScanResult, UnparsedLine
from .models import ResourceRecord
from .resources import ResourceIndex, make_record
from .utils import is_valid_block_id, normalize_url

# Conservative, explainable heuristics for block ids that name a product
# instead of a category. Each is (regex, reason).
_NAMING_RULES: list[tuple[str, str]] = [
    (r"\d{3,}", "contains a number that looks like a part or model number"),
    (r"(?:^|-)percent(?:-|$)", "contains 'percent'; category ids should not encode specifications"),
    (r"(?:^|-)datasheet$", "singular 'datasheet'; category ids should be plural, e.g. 'solar-cell-datasheets'"),
]


@dataclass(slots=True)
class Change:
    url: str
    block_ids: list[str]
    detail: str = ""

    @property
    def where(self) -> str:
        return ", ".join(self.block_ids)


@dataclass(slots=True)
class Orphan:
    record: ResourceRecord
    reason: str


@dataclass(slots=True)
class SyncReport:
    added: list[Change] = field(default_factory=list)
    moved: list[Change] = field(default_factory=list)
    updated: list[Change] = field(default_factory=list)
    orphans: list[Orphan] = field(default_factory=list)
    unparsed: list[tuple[Block, UnparsedLine]] = field(default_factory=list)
    duplicate_urls: list[tuple[str, Block]] = field(default_factory=list)
    inconsistent: list[tuple[str, list[Block], str]] = field(default_factory=list)
    duplicate_block_ids: list[tuple[str, list[Block]]] = field(default_factory=list)
    marker_problems: list[MarkerProblem] = field(default_factory=list)
    invalid_block_ids: list[tuple[Block, str]] = field(default_factory=list)
    blocks_scanned: int = 0
    entries_scanned: int = 0

    @property
    def pending(self) -> int:
        """Index changes this sync would make (or made)."""
        return len(self.added) + len(self.moved) + len(self.updated)

    @property
    def problems(self) -> int:
        """Conditions that need a human. Orphans are included: they are either
        stale records to prune or links that were removed from the site by
        mistake, and only the maintainer can tell."""
        return (
            len(self.orphans)
            + len(self.unparsed)
            + len(self.duplicate_urls)
            + len(self.inconsistent)
            + len(self.duplicate_block_ids)
            + len(self.marker_problems)
            + len(self.invalid_block_ids)
        )

    @property
    def clean(self) -> bool:
        return self.pending == 0 and self.problems == 0


def check_block_id(block_id: str) -> str | None:
    """Return a reason string if ``block_id`` violates naming conventions, else None."""
    if not is_valid_block_id(block_id):
        return "not lowercase kebab-case"
    for pattern, reason in _NAMING_RULES:
        if re.search(pattern, block_id):
            return reason
    return None


def sync(scan: ScanResult, index: ResourceIndex, apply: bool) -> SyncReport:
    """Compare the scanned site against ``index``; mutate ``index`` if ``apply``.

    The caller is responsible for ``index.write()``. Nothing is written here.
    """
    report = SyncReport(marker_problems=list(scan.problems), blocks_scanned=len(scan.blocks))
    report.duplicate_block_ids = sorted(scan.duplicate_ids().items())

    # URL → every (block, entry) it appears in, in site order.
    occurrences: dict[str, list[tuple[Block, Entry]]] = {}
    for block in scan.blocks:
        reason = check_block_id(block.block_id)
        if reason:
            report.invalid_block_ids.append((block, reason))
        for u in block.unparsed:
            report.unparsed.append((block, u))
        in_this_block: set[str] = set()
        for entry in block.entries:
            report.entries_scanned += 1
            if entry.key in in_this_block:
                report.duplicate_urls.append((entry.url, block))
                continue
            in_this_block.add(entry.key)
            occurrences.setdefault(entry.key, []).append((block, entry))

    for occ in occurrences.values():
        blocks = [b for b, _ in occ]
        first = occ[0][1]
        conflicts = {
            f"{e.title!r} vs {first.title!r}"
            if e.title != first.title
            else f"type {e.file_type} vs {first.file_type}"
            if e.file_type != first.file_type
            else f"description differs in {b.block_id}"
            for b, e in occ[1:]
            if (e.title, e.file_type, e.description) != (first.title, first.file_type, first.description)
        }
        if conflicts:
            report.inconsistent.append((first.url, blocks, "; ".join(sorted(conflicts))))
            continue  # ambiguous; reported, not applied

        block_ids = [b.block_id for b in blocks]
        existing = index.get(first.url)
        if existing is None:
            report.added.append(Change(first.url, block_ids, first.title))
            if apply:
                index.upsert(
                    make_record(
                        title=first.title,
                        description=first.description,
                        file_type=first.file_type,
                        url=first.url,
                        source=first.url,
                        block_ids=block_ids,
                        added_by="sync",
                    )
                )
            continue

        if sorted(existing.block_ids) != sorted(block_ids):
            report.moved.append(
                Change(first.url, block_ids, f"{', '.join(existing.block_ids)} → {', '.join(block_ids)}")
            )
            if apply:
                existing.block_ids = block_ids

        diffs = _visible_diffs(existing, first.title, first.file_type, first.description)
        if diffs:
            report.updated.append(Change(first.url, block_ids, ", ".join(diffs)))
            if apply:
                existing.title = first.title
                existing.file_type = first.file_type
                existing.description = first.description

    for record in index.records:
        if normalize_url(record.url) not in occurrences:
            report.orphans.append(
                Orphan(record, f"URL not found in any block (index says {', '.join(record.block_ids)})")
            )

    return report


def _visible_diffs(record: ResourceRecord, title: str, file_type: str, description: str) -> list[str]:
    diffs: list[str] = []
    if record.title != title:
        diffs.append("title")
    if record.file_type != file_type:
        diffs.append("type")
    if record.description != description:
        diffs.append("description")
    return diffs


def indexed_urls_by_block(index: ResourceIndex) -> dict[str, set[str]]:
    return {bid: {normalize_url(r.url) for r in recs} for bid, recs in index.by_block().items()}


def prune(index: ResourceIndex, orphans: list[Orphan]) -> int:
    removed = 0
    for o in orphans:
        if index.remove(o.record.url):
            removed += 1
    return removed
