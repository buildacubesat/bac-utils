# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from bac_csr_ingest import cli
from bac_csr_ingest.errors import SyncError
from bac_csr_ingest.models import ResourceDecision, SourceItem
from bac_csr_ingest.resolver import InputResolver
from bac_csr_ingest.resources import ResourceIndex
from csr_testkit import record, write_index
from typer.testing import CliRunner

from bac_common.testing import invoke

runner = CliRunner()


def run(site: Path, *args: str):
    return runner.invoke(cli.app, args, env={"CSR_REPO_ROOT": str(site)}, catch_exceptions=False)


def boundary(site: Path, monkeypatch, *args: str):
    """Through bac_common.cli.run, as the installed entry point behaves."""
    monkeypatch.setenv("CSR_REPO_ROOT", str(site))
    return invoke(cli._main, list(args))


# -- standard flags ---------------------------------------------------------


def test_version_and_help(monkeypatch, tmp_path):
    v = invoke(cli._main, ["-v"])
    assert v.exit_code == 0 and v.stdout.strip() == "bac-csr-ingest v0.4.0"
    h = invoke(cli._main, ["--help"])
    assert h.exit_code == 0
    assert "Build a CubeSat" in h.stdout
    assert "--debug" not in h.stdout
    assert len(h.stdout.rstrip().splitlines()) <= 24, h.stdout


def test_missing_config_points_to_init(monkeypatch, tmp_path):
    monkeypatch.delenv("CSR_REPO_ROOT", raising=False)
    monkeypatch.setattr("bac_common.config.CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.chdir(tmp_path)
    r = invoke(cli._main, ["check-blocks"])
    assert r.exit_code == 1
    assert "ERROR No repository configured." in r.stderr
    assert "bac-csr-ingest init" in r.stderr
    assert "Traceback" not in r.stderr


def test_argv_normalisation():
    n = cli.normalize_argv
    assert n(["file.pdf"]) == ["ingest", "file.pdf"]
    assert n(["--env-file", "x", "https://a.b"]) == ["--env-file", "x", "ingest", "https://a.b"]
    assert n(["--config=c.toml", "a.pdf", "--hint", "h"]) == ["--config=c.toml", "ingest", "a.pdf", "--hint", "h"]
    assert n(["--hint", "x", "file.pdf"]) == ["ingest", "--hint", "x", "file.pdf"]
    assert n(["--dry-run", "file.pdf"]) == ["ingest", "--dry-run", "file.pdf"]
    assert n(["sync-blocks", "--dry-run"]) == ["sync-blocks", "--dry-run"]
    assert n(["--version"]) == ["--version"]
    assert n(["-l"]) == ["-l"]
    assert n([]) == []


# -- check / sync ------------------------------------------------------------


def test_check_blocks_reports_and_exits_nonzero(site):
    r = run(site, "check-blocks")
    assert r.exit_code == 1
    assert "add" in r.output and "Problems" in r.output


def test_sync_then_check_is_clean(site):
    r = run(site, "sync-blocks")
    assert r.exit_code == 0, r.output
    assert (site / "data" / "resources.yml").exists()
    log = subprocess.run(["git", "log", "--oneline"], cwd=site, capture_output=True, text=True).stdout
    assert "sync index with site blocks (5 change(s))" in log
    assert run(site, "check-blocks").exit_code == 0


def test_sync_dry_run_writes_nothing(site):
    r = run(site, "sync-blocks", "--dry-run")
    assert r.exit_code == 0 and "dry run" in r.output
    assert not (site / "data" / "resources.yml").exists()


def test_sync_prune_requires_yes_or_confirmation(site, monkeypatch):
    write_index(site, [record("https://example.com/gone.pdf", "solar-cell-datasheets")])
    monkeypatch.setattr(cli, "confirm", lambda _m: False)
    r = boundary(site, monkeypatch, "sync-blocks", "--prune", "--no-commit")
    assert r.exit_code == 0 and "Aborted." in r.stdout
    assert ResourceIndex(site / "data" / "resources.yml").get("https://example.com/gone.pdf") is not None

    r = run(site, "sync-blocks", "--prune", "--yes", "--no-commit")
    assert r.exit_code == 0 and "Pruned" in r.output
    assert ResourceIndex(site / "data" / "resources.yml").get("https://example.com/gone.pdf") is None


def test_sync_prune_dry_run_says_what_it_would_do(site):
    write_index(site, [record("https://example.com/gone.pdf", "solar-cell-datasheets")])
    r = run(site, "sync-blocks", "--prune", "--dry-run")
    assert "Would prune 1 orphan record(s)." in r.output
    assert ResourceIndex(site / "data" / "resources.yml").get("https://example.com/gone.pdf") is not None


def test_list_blocks(site):
    r = run(site, "--list")
    assert r.output.split() == ["battery-datasheets", "solar-cell-datasheets", "link-budget-tools"]


def test_ingest_refuses_when_out_of_sync(site):
    r = runner.invoke(cli.app, ["ingest", "https://example.com/new"], env={"CSR_REPO_ROOT": str(site)})
    assert isinstance(r.exception, SyncError)


def test_ingest_out_of_sync_through_boundary(site, monkeypatch):
    r = boundary(site, monkeypatch, "https://example.com/new")
    assert r.exit_code == 1
    assert "ERROR Index is not in sync" in r.stderr
    assert "sync-blocks" in r.stderr


# -- ingest --------------------------------------------------------------------


@pytest.fixture
def fake_llm(monkeypatch):
    def classify(self, doc, blocks, sections, notify=None):
        assert doc.hint == "h"
        return ResourceDecision(
            title="New Resource",
            description="A new thing",
            resource_type="website",
            suggested_filename="new.url",
            placement_type="existing_block",
            target_block_id="link-budget-tools",
            target_markdown_file="docs/tools.md",
            reason="fits",
            confidence=0.9,
            tags=["a"],
        )

    monkeypatch.setattr(cli.LLMClassifier, "classify", classify)
    monkeypatch.setattr(
        InputResolver,
        "_resolve_url",
        lambda self, url: SourceItem(original=url, kind="external_url", source_url=url, metadata={"title": "New"}),
    )


def test_ingest_dry_run(site, fake_llm):
    run(site, "sync-blocks", "--no-commit")
    r = run(site, "ingest", "https://example.com/new", "--hint", "h", "--dry-run", "--auto-apply")
    assert r.exit_code == 0, r.output
    assert "New Resource" in r.output and "dry run" in r.output
    assert "example.com/new" not in (site / "docs" / "tools.md").read_text()


def test_ingest_external_link_end_to_end(site, fake_llm):
    run(site, "sync-blocks", "--no-commit")
    r = run(site, "ingest", "https://example.com/new", "--hint", "h", "--yes")
    assert r.exit_code == 0, r.output
    tools = (site / "docs" / "tools.md").read_text()
    assert "- **[New Resource](https://example.com/new)** `Link` – A new thing" in tools
    assert "AMSAT link budget" in tools  # existing manual entry preserved
    rec = ResourceIndex(site / "data" / "resources.yml").get("https://example.com/new")
    assert rec.block_ids == ["link-budget-tools"] and rec.tags == ["a"] and rec.added_by == "ingest"
    log = subprocess.run(["git", "log", "--oneline"], cwd=site, capture_output=True, text=True).stdout
    assert "Tools: Add New Resource" in log
    assert run(site, "check-blocks").exit_code == 0
    # Second run is a no-op thanks to pre-flight dedup.
    r = run(site, "ingest", "https://example.com/new", "--hint", "h", "--yes")
    assert "Already indexed" in r.output and "Nothing to do" in r.output


def test_ingest_hostile_title_is_neutralised(site, monkeypatch):
    def classify(self, doc, blocks, sections, notify=None):
        return ResourceDecision.model_validate(
            {
                "title": "Evil <img src=x onerror=alert(1)> [x]\nsecond line",
                "description": "<script>alert(1)</script>Plain",
                "suggested_filename": "e.url",
                "placement_type": "existing_block",
                "target_block_id": "link-budget-tools",
                "target_markdown_file": "docs/tools.md",
                "reason": "fits here",
                "confidence": 0.5,
            }
        )

    monkeypatch.setattr(cli.LLMClassifier, "classify", classify)
    monkeypatch.setattr(
        InputResolver,
        "_resolve_url",
        lambda self, url: SourceItem(original=url, kind="external_url", source_url=url),
    )
    run(site, "sync-blocks", "--no-commit")
    r = run(site, "ingest", "https://example.com/evil", "--yes", "--no-commit")
    assert r.exit_code == 0, r.output
    tools = (site / "docs" / "tools.md").read_text()
    body = tools.split("<!-- CSR-RESOURCES:START link-budget-tools -->")[1].split("<!-- CSR-RESOURCES:END")[0]
    assert "<" not in body and "\n\n" not in body.strip()
    assert "- **[Evil (x) second line](https://example.com/evil)** `Link` – Plain" in tools


def test_ingest_summary_printed_on_failure(site, fake_llm, monkeypatch):
    run(site, "sync-blocks", "--no-commit")

    def boom(*a, **k):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(cli.RepoContext, "render_blocks", boom)
    r = boundary(site, monkeypatch, "https://example.com/new", "--hint", "h", "--yes", "--no-commit")
    assert r.exit_code == 1
    assert "Linked" in r.stdout and "Commits" in r.stdout  # summary block reached
    assert "ERROR Unexpected error: render exploded" in r.stderr


def test_ingest_unknown_block_fails_before_writing(site, monkeypatch):
    def classify(self, doc, blocks, sections, notify=None):
        return ResourceDecision(
            title="Thing",
            description="Desc",
            suggested_filename="t.url",
            placement_type="existing_block",
            target_block_id="no-such-block",
            target_markdown_file="docs/tools.md",
            reason="fits here",
            confidence=0.5,
        )

    monkeypatch.setattr(cli.LLMClassifier, "classify", classify)
    monkeypatch.setattr(
        InputResolver, "_resolve_url", lambda self, url: SourceItem(original=url, kind="external_url", source_url=url)
    )
    run(site, "sync-blocks", "--no-commit")
    before = (site / "docs" / "tools.md").read_text()
    r = boundary(site, monkeypatch, "https://example.com/x", "--yes", "--no-commit")
    assert r.exit_code == 1
    assert "ERROR Unknown block id: no-such-block" in r.stderr
    assert (site / "docs" / "tools.md").read_text() == before
