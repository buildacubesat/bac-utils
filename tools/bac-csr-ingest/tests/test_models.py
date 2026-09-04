# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from bac_csr_ingest.models import ResourceDecision, check_rel_md, clean_text
from pydantic import ValidationError

BASE = {
    "title": "A fine title",
    "description": "A description",
    "suggested_filename": "file.pdf",
    "placement_type": "existing_block",
    "target_block_id": "solar-cell-datasheets",
    "target_markdown_file": "docs/eps.md",
    "reason": "fits",
    "confidence": 0.8,
}


def decision(**overrides) -> ResourceDecision:
    return ResourceDecision.model_validate({**BASE, **overrides})


def test_clean_text_strips_html_and_control_characters():
    assert clean_text("Hello <b>world</b>\nnext\ttab") == "Hello world next tab"
    assert clean_text("a < b > c") == "a b c"
    assert clean_text("x <script>evil()</script> y <style>z</style>") == "x y"
    assert clean_text("  many   spaces ") == "many spaces"


def test_clean_text_link_safe():
    assert clean_text("GNSS [Draft] `code` **bold**", link_safe=True) == "GNSS (Draft) 'code' bold"


def test_title_and_description_are_sanitised():
    d = decision(title="Evil <img src=x onerror=alert(1)> [x]", description="<script>x</script>Plain text")
    assert d.title == "Evil (x)"
    assert d.description == "Plain text"


def test_sanitised_title_must_still_meet_min_length():
    with pytest.raises(ValidationError):
        decision(title="<b></b>")


def test_optional_text_fields_become_none_when_empty():
    d = decision(publisher="<i></i>", author="  ", suggested_heading=None)
    assert d.publisher is None and d.author is None and d.suggested_heading is None


def test_tags_cleaned_deduplicated_and_capped():
    d = decision(tags=["<b>eps</b>", "EPS", "  ", "x" * 80, 5])
    assert d.tags[0] == "eps"
    assert len(d.tags) == 2
    assert len(d.tags[1]) == 40


def test_block_ids_must_be_kebab_case():
    with pytest.raises(ValidationError, match="kebab-case"):
        decision(target_block_id="Solar Cells")
    with pytest.raises(ValidationError, match="kebab-case"):
        decision(placement_type="new_block_requested", suggested_block_id="../x", suggested_parent_file="docs/a.md")
    assert decision(target_block_id="ok-id-1").target_block_id == "ok-id-1"


def test_paths_are_shape_checked():
    with pytest.raises(ValidationError, match="absolute"):
        decision(target_markdown_file="/etc/passwd.md")
    with pytest.raises(ValidationError, match="'..'"):
        decision(target_markdown_file="docs/../README.md")
    with pytest.raises(ValidationError, match=".md"):
        decision(target_markdown_file="docs/x.txt")
    assert decision(target_markdown_file=" docs/sub/x.md ").target_markdown_file == "docs/sub/x.md"


def test_check_rel_md_rejects_backslashes_and_control_chars():
    with pytest.raises(ValueError):
        check_rel_md("docs\\x.md")
    with pytest.raises(ValueError):
        check_rel_md("docs/x\n.md")


def test_validate_on_assignment():
    d = decision()
    with pytest.raises(ValidationError):
        d.title = "<b></b>"
    d.title = "Fine <b>again</b>"
    assert d.title == "Fine again"
    with pytest.raises(ValidationError):
        d.year = 99999
    with pytest.raises(ValidationError):
        d.suggested_block_id = "Not Kebab"


def test_newline_in_title_cannot_break_the_block_line():
    d = decision(title="line one\nline two")
    assert "\n" not in d.title
