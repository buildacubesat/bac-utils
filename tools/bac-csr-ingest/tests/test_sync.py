# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest
from bac_csr_ingest.errors import SyncError
from bac_csr_ingest.repo import RepoContext
from bac_csr_ingest.resources import ResourceIndex
from bac_csr_ingest.sync import check_block_id, indexed_urls_by_block, prune, sync
from csr_testkit import record, write_index


def ctx(site: Path):
    return RepoContext(site, site / "docs"), ResourceIndex(site / "data" / "resources.yml")


def test_sync_backfills_empty_index(site):
    repo, index = ctx(site)
    report = sync(repo.scan(), index, apply=True)
    assert report.blocks_scanned == 3 and report.entries_scanned == 5
    assert len(report.added) == 5 and report.problems == 0
    index.write()
    reloaded = ResourceIndex(site / "data" / "resources.yml")
    r = reloaded.get("https://example.com/p42a.pdf")
    assert r.block_ids == ["battery-datasheets"] and r.file_type == "PDF" and r.added_by == "sync" and r.sha256 is None
    assert reloaded.get("https://batteryuniversity.com").file_type == "Link"  # trailing slash normalised
    # Idempotent
    assert sync(repo.scan(), reloaded, apply=False).clean


def test_sync_is_read_only_for_markdown(site):
    before = (site / "docs" / "eps.md").read_text()
    repo, index = ctx(site)
    sync(repo.scan(), index, apply=True)
    assert (site / "docs" / "eps.md").read_text() == before


def test_sync_detects_move_update_orphan(site):
    write_index(
        site,
        [
            record("https://example.com/3g30c.pdf", "battery-datasheets", title="Old title"),
            record("https://example.com/gone.pdf", "solar-cell-datasheets"),
        ],
    )
    repo, index = ctx(site)
    report = sync(repo.scan(), index, apply=False)
    assert [c.detail for c in report.moved] == ["battery-datasheets → solar-cell-datasheets"]
    assert report.updated and "title" in report.updated[0].detail
    assert [o.record.url for o in report.orphans] == ["https://example.com/gone.pdf"]
    assert not report.clean
    sync(repo.scan(), index, apply=True)
    assert index.get("https://example.com/3g30c.pdf").block_ids == ["solar-cell-datasheets"]
    assert prune(index, report.orphans) == 1 and index.get("https://example.com/gone.pdf") is None


def test_sync_reports_unparsed_and_inconsistent_crosslisting(site):
    md = site / "docs" / "tools.md"
    md.write_text(
        md.read_text().replace(
            "<!-- CSR-RESOURCES:END link-budget-tools -->",
            "- **[Dup](https://example.com/3g30c.pdf)** `PDF`\n<!-- CSR-RESOURCES:END link-budget-tools -->\nSome stray prose\n<!-- CSR-RESOURCES:START x -->\nprose first\n<!-- CSR-RESOURCES:END x -->",
        )
    )
    repo, index = ctx(site)
    report = sync(repo.scan(), index, apply=True)
    assert [u.raw for _, u in report.unparsed] == ["prose first"]
    assert len(report.inconsistent) == 1 and "'Dup' vs 'Azur 3G30C'" in report.inconsistent[0][2]
    assert index.get("https://example.com/3g30c.pdf") is None  # ambiguous entries are not applied


def test_sync_crosslisting_and_continuation(site):
    md = site / "docs" / "tools.md"
    md.write_text(
        md.read_text().replace(
            "<!-- CSR-RESOURCES:END link-budget-tools -->",
            "- **[Azur 3G30C](https://example.com/3g30c.pdf)** `PDF` – Triple-junction cell\n"
            "- **[Paren](https://example.com/Rev.1(31May2022).pdf)**\n  Description on the next line.\n"
            "<!-- CSR-RESOURCES:END link-budget-tools -->",
        )
    )
    repo, index = ctx(site)
    report = sync(repo.scan(), index, apply=True)
    assert report.problems == 0
    assert index.get("https://example.com/3g30c.pdf").block_ids == ["solar-cell-datasheets", "link-budget-tools"]
    paren = index.get("https://example.com/Rev.1(31May2022).pdf")
    assert paren.description == "Description on the next line." and paren.file_type == "PDF"
    # Same URL twice in one block is still an error.
    md.write_text(
        md.read_text().replace(
            "- **[Paren]", "- **[Azur 3G30C](https://example.com/3g30c.pdf)** `PDF` – Triple-junction cell\n- **[Paren]"
        )
    )
    assert len(sync(repo.scan(), ResourceIndex(site / "data" / "resources.yml"), apply=False).duplicate_urls) == 1


def test_render_crosslisted_entry_in_both_blocks(site):
    md = site / "docs" / "tools.md"
    md.write_text(
        md.read_text().replace(
            "<!-- CSR-RESOURCES:END link-budget-tools -->",
            "- [Azur 3G30C](https://example.com/3g30c.pdf) - Triple-junction cell\n<!-- CSR-RESOURCES:END link-budget-tools -->",
        )
    )
    repo, index = ctx(site)
    sync(repo.scan(), index, apply=True)
    repo.render_blocks(index.rendered_lines_by_block(), indexed_urls_by_block(index))
    canonical = "- **[Azur 3G30C](https://example.com/3g30c.pdf)** `PDF` – Triple-junction cell"
    assert canonical in (site / "docs" / "tools.md").read_text()
    assert canonical in (site / "docs" / "eps.md").read_text()
    assert sync(repo.scan(), index, apply=False).clean


def test_check_block_id():
    assert check_block_id("solar-cell-datasheets") is None
    assert check_block_id("Solar_Cells") is not None
    assert "number" in check_block_id("lightfoundry-space-grade-30-percent-gaas-14466-datasheet")
    assert "plural" in check_block_id("gaas-datasheet")


def test_render_refuses_out_of_sync_block(site):
    repo, index = ctx(site)
    with pytest.raises(SyncError, match="not indexed"):
        repo.render_blocks({}, indexed_urls_by_block(index), only={"battery-datasheets"})


def test_render_refuses_unparsed_and_duplicate_ids(site):
    md = site / "docs" / "tools.md"
    md.write_text(
        md.read_text()
        + "\n<!-- CSR-RESOURCES:START solar-cell-datasheets -->\n<!-- CSR-RESOURCES:END solar-cell-datasheets -->\n"
    )
    repo, index = ctx(site)
    sync(repo.scan(), index, apply=True)
    with pytest.raises(SyncError, match="more than once"):
        repo.render_blocks(
            index.rendered_lines_by_block(), indexed_urls_by_block(index), only={"solar-cell-datasheets"}
        )


def test_render_after_sync_normalises_only_target_block(site):
    repo, index = ctx(site)
    sync(repo.scan(), index, apply=True)
    tools_before = (site / "docs" / "tools.md").read_text()
    changed = repo.render_blocks(
        index.rendered_lines_by_block(), indexed_urls_by_block(index), only={"battery-datasheets"}
    )
    assert changed == ["docs/eps.md"]
    eps = (site / "docs" / "eps.md").read_text()
    assert "- **[Molicel P42A](https://example.com/p42a.pdf)** `PDF` – Manual entry without bold or type" in eps
    assert "inline link" in eps and "## Solar" in eps
    assert (site / "docs" / "tools.md").read_text() == tools_before
    # Render is a fixed point: a second sync finds nothing to do.
    assert sync(repo.scan(), index, apply=False).clean
