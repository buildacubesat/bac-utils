# SPDX-License-Identifier: MIT
"""Pure planning helpers for ``ingest``: what goes where, under which name, in which commit.

Nothing here touches the network, the filesystem or the terminal beyond
:func:`print_plan`, so all of it is unit-testable without a site.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from bac_common import ui

from .config import Config
from .errors import PlacementError
from .models import ExtractedDocument, ResourceDecision, ResourceRecord
from .repo import RepoContext
from .resources import ResourceIndex, make_record
from .utils import safe_filename, short_hash

__all__ = [
    "PlannedItem",
    "make_plan_item",
    "resolve_block_id",
    "is_external_document",
    "is_external_link",
    "validate_placements",
    "already_indexed",
    "record_for",
    "section_name_for_item",
    "group_planned_by_section",
    "commit_subject_for_group",
    "print_plan",
    "rel",
]


@dataclass(slots=True)
class PlannedItem:
    document: ExtractedDocument
    decision: ResourceDecision
    block_id: str
    markdown_file: str | None
    blob_name: str
    public_url: str


# ---------------------------------------------------------------------------
# Building the plan
# ---------------------------------------------------------------------------


def make_plan_item(
    cfg: Config, doc: ExtractedDocument, decision: ResourceDecision, used_blob_names: set[str]
) -> PlannedItem:
    block_id = resolve_block_id(decision)
    if is_external_document(doc):
        blob_name = ""
        public_url = doc.source.source_url or doc.source.original
    else:
        filename = safe_filename(decision.suggested_filename, doc.extension)
        blob_name = f"{cfg.gcs_prefix.strip('/')}/{block_id}/{filename}"
        if blob_name in used_blob_names:
            blob_name = hashed_blob_name(blob_name, doc.sha256)
        used_blob_names.add(blob_name)
        public_url = f"{(cfg.public_base_url or '').rstrip('/')}/{blob_name}"

    return PlannedItem(
        document=doc,
        decision=decision,
        block_id=block_id,
        markdown_file=decision.target_markdown_file or decision.suggested_parent_file or decision.suggested_path,
        blob_name=blob_name,
        public_url=public_url,
    )


def hashed_blob_name(blob_name: str, sha256: str) -> str:
    """``resources/x/file.pdf`` → ``resources/x/file-1a2b3c4d.pdf``."""
    p = Path(blob_name)
    return f"{p.with_suffix('').as_posix()}-{short_hash(sha256)}{p.suffix}"


def is_external_document(doc: ExtractedDocument) -> bool:
    return doc.source.kind == "external_url"


def is_external_link(item: PlannedItem) -> bool:
    return is_external_document(item.document)


def resolve_block_id(decision: ResourceDecision) -> str:
    """The block the item lands in. Ids are already kebab-checked by the model validators."""
    if decision.placement_type == "existing_block":
        if not decision.target_block_id:
            raise PlacementError("Placement decision is missing target_block_id for existing_block.")
        return decision.target_block_id
    if not decision.suggested_block_id:
        raise PlacementError(f"Placement decision is missing suggested_block_id for {decision.placement_type}.")
    return decision.suggested_block_id


def validate_placements(planned: list[PlannedItem], repo: RepoContext, known_blocks: dict[str, str]) -> None:
    """Check every placement against the repository before anything is uploaded or written.

    Sets ``markdown_file`` on each item from what the repository knows, not
    from what the classifier claimed. ``known_blocks`` maps block id to file
    and is extended with the blocks this plan will create, so two items may
    share a new block.
    """
    for item in planned:
        d = item.decision
        if d.placement_type == "existing_block":
            if item.block_id not in known_blocks:
                raise PlacementError(
                    f"Unknown block id: {item.block_id}", "Run check-blocks to list the site's blocks."
                )
            item.markdown_file = known_blocks[item.block_id]
        elif d.placement_type == "new_block_requested":
            if item.block_id in known_blocks:
                item.markdown_file = known_blocks[item.block_id]
                continue
            parent = repo.require_docs_md(d.suggested_parent_file, must_exist=True)
            item.markdown_file = known_blocks[item.block_id] = parent
        elif d.placement_type == "new_page_requested":
            if item.block_id in known_blocks:
                item.markdown_file = known_blocks[item.block_id]
                continue
            path = repo.require_docs_md(d.suggested_path, must_exist=False)
            item.markdown_file = known_blocks[item.block_id] = path
        else:  # pragma: no cover – Literal type forbids it
            raise PlacementError(f"Unsupported placement type: {d.placement_type}")


def already_indexed(index: ResourceIndex, doc: ExtractedDocument) -> str | None:
    """Block ids of an existing record for this document, by source URL, original input, or hash."""
    candidates = [doc.source.source_url, doc.source.original if doc.source.kind == "url_document" else None]
    for url in candidates:
        if url:
            r = index.get(url)
            if r:
                return ", ".join(r.block_ids)
    r = index.find_by_sha(doc.sha256)
    return ", ".join(r.block_ids) if r else None


def record_for(item: PlannedItem) -> ResourceRecord:
    d = item.decision
    return make_record(
        title=d.title,
        description=d.description,
        file_type="link" if is_external_link(item) else item.document.extension,
        url=item.public_url,
        source=item.document.source.source_url or item.document.source.original,
        block_ids=[item.block_id],
        publisher=d.publisher,
        author=d.author,
        year=d.year,
        resource_type=d.resource_type,
        tags=d.tags,
        sha256=item.document.sha256,
        added_by="ingest",
    )


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Commit grouping
# ---------------------------------------------------------------------------

SECTION_OVERRIDES = {
    "adcs": "ADCS",
    "cdh": "C&DH",
    "c&dh": "C&DH",
    "comms": "Comms",
    "eps": "EPS",
    "gnc": "GNC",
    "obc": "OBC",
    "tvac": "TVAC",
    "ground segment": "Ground Segment",
}


def section_name_for_item(item: PlannedItem) -> str:
    stem = Path(item.markdown_file or "").stem.replace("-", " ").strip()
    name = stem.title() if stem else "Resources"
    return SECTION_OVERRIDES.get(name.lower(), name)


def group_planned_by_section(planned: list[PlannedItem]) -> dict[str, list[PlannedItem]]:
    grouped: dict[str, list[PlannedItem]] = {}
    for item in planned:
        grouped.setdefault(section_name_for_item(item), []).append(item)
    return grouped


def commit_subject_for_group(section: str, items: list[PlannedItem]) -> str:
    return f"{section}: Add {human_join(dedupe_preserve_order(short_resource_name(i) for i in items))}"


def short_resource_name(item: PlannedItem) -> str:
    d = item.decision
    if d.resource_type == "datasheet" and (d.publisher or "").strip():
        return f"{(d.publisher or '').strip()} datasheet"
    return shorten_commit_fragment(d.title.strip() or d.resource_type or "resource")


def shorten_commit_fragment(value: str, max_length: int = 48) -> str:
    value = " ".join(value.split())
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip(" ,.;:-") + "…"


def human_join(values: Iterable[str]) -> str:
    items = [v for v in values if v]
    if not items:
        return "resources"
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------


def print_plan(planned: list[PlannedItem]) -> None:
    rows = []
    for item in planned:
        src = item.document.source
        source = src.source_url or Path(src.original).name
        rows.append(
            [
                ui.esc(source[:60]),
                ui.esc(item.decision.title[:60]),
                ui.esc(f"{item.decision.placement_type} → {item.block_id}"),
                "Link" if is_external_link(item) else ui.esc(Path(item.blob_name).name),
                f"{item.decision.confidence:.2f}",
            ]
        )
    ui.table(
        "Ingest plan",
        [("Source", 3), ("Title", 3), ("Placement", 4), ("Filename", 2), ("Conf.", 0, "right")],
        rows,
    )
    for item in planned:
        if item.decision.placement_type != "existing_block":
            ui.warn(
                f"New placement: {ui.esc(item.decision.placement_type)} → "
                f"{ui.path(item.markdown_file or '(no file)')} / {ui.esc(item.block_id)}"
            )
            ui.dim(f"    Reason: {ui.esc(item.decision.reason)}")
