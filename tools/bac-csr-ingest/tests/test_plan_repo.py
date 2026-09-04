# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest
from bac_csr_ingest.config import Config
from bac_csr_ingest.errors import PlacementError
from bac_csr_ingest.models import ExtractedDocument, ResourceDecision, SourceItem
from bac_csr_ingest.plan import (
    commit_subject_for_group,
    hashed_blob_name,
    make_plan_item,
    section_name_for_item,
    validate_placements,
)
from bac_csr_ingest.repo import RepoContext


def doc(name: str = "a.pdf", kind: str = "local_file", sha: str = "f" * 64) -> ExtractedDocument:
    src = SourceItem(original=name, kind=kind, staged_path=Path(name), source_url=None)  # type: ignore[arg-type]
    return ExtractedDocument(
        source=src, title_hint=None, content_excerpt="", sha256=sha, extension=".pdf", size_bytes=1
    )


def dec(**kw) -> ResourceDecision:
    base = {
        "title": "Panasonic NCR18650B",
        "description": "Cell datasheet",
        "suggested_filename": "ncr18650b.pdf",
        "placement_type": "existing_block",
        "target_block_id": "battery-datasheets",
        "target_markdown_file": "docs/eps.md",
        "reason": "fits here",
        "confidence": 0.9,
    }
    return ResourceDecision.model_validate({**base, **kw})


def cfg(tmp_path: Path) -> Config:
    return Config(repo_root=tmp_path, bucket_name="b", public_base_url="https://cdn.example/", gcs_prefix="/res/")


def test_blob_name_and_collision_suffix(tmp_path):
    used: set[str] = set()
    a = make_plan_item(cfg(tmp_path), doc(sha="a" * 64), dec(), used)
    b = make_plan_item(cfg(tmp_path), doc(sha="b" * 64), dec(), used)
    assert a.blob_name == "res/battery-datasheets/ncr18650b.pdf"
    assert a.public_url == "https://cdn.example/res/battery-datasheets/ncr18650b.pdf"
    assert b.blob_name.startswith("res/battery-datasheets/ncr18650b-") and b.blob_name.endswith(".pdf")
    assert hashed_blob_name("x/y.pdf", "0" * 64) == "x/y-60e05bd1.pdf"


def test_external_document_has_no_blob(tmp_path):
    d = doc("https://x.y/z", kind="external_url")
    d.source.source_url = "https://x.y/z"
    item = make_plan_item(cfg(tmp_path), d, dec(), set())
    assert item.blob_name == "" and item.public_url == "https://x.y/z"


def test_commit_subjects():
    items = [
        make_plan_item(cfg(Path("/tmp")), doc(), dec(resource_type="datasheet", publisher="Panasonic"), set()),
        make_plan_item(cfg(Path("/tmp")), doc(sha="1" * 64), dec(title="Molicel P42A"), set()),
        make_plan_item(cfg(Path("/tmp")), doc(sha="2" * 64), dec(title="A " * 40), set()),
    ]
    for i in items:
        i.markdown_file = "docs/eps.md"
    assert section_name_for_item(items[0]) == "EPS"
    subject = commit_subject_for_group("EPS", items)
    assert subject.startswith("EPS: Add Panasonic datasheet, Molicel P42A, and A A A")
    assert subject.endswith("…")


def test_validate_placements_sets_files_from_repo(site):
    repo = RepoContext(site, site / "docs")
    known = {b.block_id: b.file for b in repo.scan().blocks}
    item = make_plan_item(cfg(site), doc(), dec(target_markdown_file="docs/wrong.md"), set())
    validate_placements([item], repo, known)
    assert item.markdown_file == "docs/eps.md"  # what the repo says, not what the LLM claimed


def test_validate_placements_rejects_unknown_block(site):
    repo = RepoContext(site, site / "docs")
    item = make_plan_item(cfg(site), doc(), dec(target_block_id="nope"), set())
    with pytest.raises(PlacementError, match="Unknown block id"):
        validate_placements([item], repo, {})


def test_validate_placements_new_block_needs_existing_parent(site):
    repo = RepoContext(site, site / "docs")
    d = dec(
        placement_type="new_block_requested",
        target_block_id=None,
        target_markdown_file=None,
        suggested_parent_file="docs/missing.md",
        suggested_heading="Radios",
        suggested_block_id="radio-datasheets",
    )
    item = make_plan_item(cfg(site), doc(), d, set())
    with pytest.raises(PlacementError, match="Parent page does not exist"):
        validate_placements([item], repo, {})
    d2 = d.model_copy(update={"suggested_parent_file": "docs/eps.md"})
    item2 = make_plan_item(cfg(site), doc(), d2, set())
    known: dict[str, str] = {}
    validate_placements([item2], repo, known)
    assert item2.markdown_file == "docs/eps.md" and known["radio-datasheets"] == "docs/eps.md"


def test_require_docs_md_scope(site):
    repo = RepoContext(site, site / "docs")
    assert repo.require_docs_md("docs/eps.md", must_exist=True) == "docs/eps.md"
    assert repo.require_docs_md("docs/new/page.md", must_exist=False) == "docs/new/page.md"
    with pytest.raises(PlacementError, match="outside the docs directory"):
        repo.require_docs_md("README.md", must_exist=False)
    with pytest.raises(PlacementError, match="Refusing"):
        repo.require_docs_md("docs/../mkdocs.yml", must_exist=False)
    with pytest.raises(PlacementError, match="Refusing"):
        repo.require_docs_md("/etc/x.md", must_exist=False)
    with pytest.raises(PlacementError, match="Missing"):
        repo.require_docs_md(None, must_exist=False)
