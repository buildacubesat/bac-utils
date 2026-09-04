# SPDX-License-Identifier: MIT
"""Interactive review of classifier decisions (InquirerPy).

Edits go through :class:`ResourceDecision`'s validators because the model
validates on assignment; an edit that fails validation is reported and the
previous value is kept, so a typo cannot smuggle an invalid value past the
same rules the classifier's output must satisfy.
"""

from __future__ import annotations

from InquirerPy import inquirer
from pydantic import ValidationError

from bac_common import ui

from .errors import PlacementError, SkipItem
from .models import BlockTarget, ResourceDecision

__all__ = ["review", "confirm", "review_decision", "edit_common_metadata", "set_field"]


def review(decision: ResourceDecision, blocks: list[BlockTarget], *, auto_apply: bool, yes: bool) -> ResourceDecision:
    """``--yes`` accepts everything; ``--auto-apply`` only asks about new blocks/pages; default asks about all."""
    if yes:
        return decision
    if auto_apply:
        return decision if decision.placement_type == "existing_block" else review_new_placement_decision(decision)
    return review_decision(decision, blocks)


def review_decision(decision: ResourceDecision, blocks: list[BlockTarget]) -> ResourceDecision:
    if decision.placement_type == "existing_block":
        return review_existing_block_decision(decision, blocks)
    return review_new_placement_decision(decision)


def review_existing_block_decision(decision: ResourceDecision, blocks: list[BlockTarget]) -> ResourceDecision:
    ui.console.print()
    ui.fields(
        [
            ("Resource", decision.title),
            ("Placement", f"existing_block → {decision.target_block_id}"),
            ("File", decision.target_markdown_file),
            ("Reason", decision.reason),
        ]
    )

    action = inquirer.select(
        message="Placement:", choices=["Accept", "Change block", "Edit metadata", "Skip"], default="Accept"
    ).execute()
    if action == "Skip":
        raise SkipItem()

    if action == "Change block":
        if not blocks:
            ui.warn("No existing resource blocks available.")
            raise SkipItem()
        choices = [{"name": f"{b.block_id} – {b.file}", "value": b.block_id} for b in blocks]
        selected = inquirer.select(message="Target block:", choices=choices, default=decision.target_block_id).execute()
        block = next(b for b in blocks if b.block_id == selected)
        set_field(decision, "target_block_id", block.block_id)
        set_field(decision, "target_markdown_file", block.file)
        set_field(decision, "placement_type", "existing_block")

    if action in {"Change block", "Edit metadata"}:
        decision = edit_common_metadata(decision)
    return decision


def review_new_placement_decision(decision: ResourceDecision) -> ResourceDecision:
    ui.console.print()
    ui.warn("[bold]New placement requested[/bold]")
    ui.fields(
        [
            ("Resource", decision.title),
            ("Type", decision.placement_type),
            ("Parent file", decision.suggested_parent_file or decision.suggested_path),
            ("Parent heading", decision.suggested_parent_heading),
            ("New heading", decision.suggested_heading),
            ("Block ID", decision.suggested_block_id),
            ("Reason", decision.reason),
        ]
    )

    action = inquirer.select(message="New placement:", choices=["Accept", "Edit", "Skip"], default="Accept").execute()
    if action == "Skip":
        raise SkipItem()
    if action == "Edit":
        decision = edit_new_placement(decision)
    return decision


def _text(message: str, default: str | None) -> str:
    return inquirer.text(message=message, default=default or "").execute().strip()


def set_field(decision: ResourceDecision, name: str, value: object) -> bool:
    """Assign through the model's validators; keep the old value and warn on failure."""
    try:
        setattr(decision, name, value)
    except ValidationError as exc:
        reason = exc.errors()[0].get("msg", "invalid value") if exc.errors() else "invalid value"
        ui.warn(f"{ui.esc(name)}: {ui.esc(str(reason))} – keeping {ui.esc(repr(getattr(decision, name)))}")
        return False
    return True


def edit_new_placement(decision: ResourceDecision) -> ResourceDecision:
    placement_type = inquirer.select(
        message="Placement type:",
        choices=["new_block_requested", "new_page_requested", "existing_block"],
        default=decision.placement_type,
    ).execute()
    set_field(decision, "placement_type", placement_type)

    if placement_type == "new_block_requested":
        set_field(
            decision,
            "suggested_parent_file",
            _text("Parent file:", decision.suggested_parent_file or decision.target_markdown_file),
        )
        set_field(
            decision, "suggested_parent_heading", _text("Parent heading:", decision.suggested_parent_heading) or None
        )
        set_field(decision, "suggested_heading", _text("New block heading:", decision.suggested_heading or "Resources"))
        set_field(decision, "suggested_block_id", _text("Block ID:", decision.suggested_block_id))
        for name in ("target_block_id", "target_markdown_file", "suggested_path", "suggested_nav_title"):
            set_field(decision, name, None)
    elif placement_type == "new_page_requested":
        set_field(decision, "suggested_path", _text("New page path:", decision.suggested_path))
        set_field(
            decision, "suggested_nav_title", _text("Navigation title:", decision.suggested_nav_title or decision.title)
        )
        set_field(
            decision,
            "suggested_heading",
            _text("Page heading:", decision.suggested_heading or decision.suggested_nav_title),
        )
        set_field(decision, "suggested_block_id", _text("Block ID:", decision.suggested_block_id))
        for name in ("target_block_id", "target_markdown_file", "suggested_parent_file", "suggested_parent_heading"):
            set_field(decision, name, None)
    elif placement_type == "existing_block":
        set_field(
            decision,
            "target_block_id",
            _text("Existing block ID:", decision.target_block_id or decision.suggested_block_id),
        )
        set_field(
            decision,
            "target_markdown_file",
            _text("Existing Markdown file:", decision.target_markdown_file or decision.suggested_parent_file),
        )
        for name in (
            "suggested_block_id",
            "suggested_parent_file",
            "suggested_parent_heading",
            "suggested_path",
            "suggested_nav_title",
            "suggested_heading",
        ):
            set_field(decision, name, None)
    else:
        raise PlacementError(f"Unsupported placement_type: {placement_type}")

    return edit_common_metadata(decision)


def edit_common_metadata(decision: ResourceDecision) -> ResourceDecision:
    set_field(decision, "title", _text("Title:", decision.title))
    set_field(decision, "description", _text("Description:", decision.description))
    set_field(decision, "suggested_filename", _text("Filename:", decision.suggested_filename))
    set_field(decision, "resource_type", _text("Resource type:", decision.resource_type) or None)
    set_field(decision, "publisher", _text("Publisher:", decision.publisher) or None)
    set_field(decision, "author", _text("Author:", decision.author) or None)
    year = _text("Year:", str(decision.year or ""))
    set_field(decision, "year", int(year) if year.isdigit() else None)
    tags = _text("Tags, comma-separated:", ", ".join(decision.tags))
    set_field(decision, "tags", [t.strip() for t in tags.split(",") if t.strip()])
    return decision


def confirm(message: str) -> bool:
    return bool(inquirer.confirm(message=message, default=False).execute())
