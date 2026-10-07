# SPDX-License-Identifier: MIT
"""The notebook headless on both backends, with the fixture's numbers."""

from __future__ import annotations

import pytest
from bac_pricing import NOTEBOOK, __version__, store
from pricing_testkit import FIXTURES, run_notebook, write_db_config, write_files_config

from bac_suite_db import config, schema


def test_notebook_file_conventions():
    text = NOTEBOOK.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "# SPDX-License-Identifier: MIT"
    assert f'TOOL_VERSION = "{__version__}"' in text
    assert "light-dark(" in text and "--heading-font" in text and ".vega-embed text" in text
    retired = ("--amber", "#F59E0B")  # convention-check: allow F1 – the retired names must be gone
    assert not any(name in text for name in retired)
    assert "\u2014" not in text
    assert "mo.ui.file_browser" not in text  # the data directory comes from the suite config
    for label in ('label="BOM structure', 'label="Vendor table', 'label="Exchange rates'):
        assert label in text
    assert text.count("mo.ui.data_editor(") == 6  # the six editors, each with a label above


def test_runs_headless_in_files_mode(tmp_path):
    cfg = write_files_config(tmp_path, FIXTURES)
    defs = run_notebook(cfg)
    assert defs["pr"].valid and defs["pr"].price_rounded == 1138.0
    assert defs["batch"] == 25 and defs["root"] == "dev_kit_v1"
    assert defs["problems"] == []
    assert defs["storage_lines"][0].startswith("Files ·")
    assert {r["region"]: r["price"] for r in defs["regions"]}["CH"] == 1138.0
    assert defs["fx_source"] == "manual" and defs["model"].cfg["fx"]["updated"] == "2026-06-04"


def test_runs_headless_in_db_mode(tmp_path, fake_conn, monkeypatch):
    schema.migrate(fake_conn, [store.ENGINE])
    store.import_files(fake_conn, FIXTURES)
    monkeypatch.setenv(config.DSN_ENV, "postgresql://bac:secret@db.example:5432/bac")
    cfg = write_db_config(tmp_path, tmp_path)
    defs = run_notebook(cfg)
    assert defs["pr"].price_rounded == 1138.0
    assert defs["storage_lines"][0] == "Postgres · db.example:5432/bac"
    assert "secret" not in " ".join(defs["storage_lines"])
    assert defs["storage_lines"][1].startswith("params: v1 ·")


def test_stops_with_a_callout_when_storage_is_unreachable(tmp_path):
    cfg = write_db_config(tmp_path, tmp_path)  # no DSN at all
    defs = run_notebook(cfg)
    assert "model_src" not in defs or defs.get("model_src") is None
    assert "pr" not in defs


@pytest.mark.parametrize("name", ["bac-link-budget", "bac-power-budget"])
def test_style_cell_matches_the_notebooks_group(name):
    """The style cell is the class's shared text; only the two pricing-specific rules are appended."""
    from pathlib import Path

    sibling = Path(__file__).resolve().parents[3] / "notebooks" / name / f"{name.replace('-', '_')}.py"
    if not sibling.exists():
        pytest.skip("notebooks group not checked out")
    ours = NOTEBOOK.read_text(encoding="utf-8")
    theirs = sibling.read_text(encoding="utf-8")
    start, end = ours.index("<style>"), ours.index(".bac-sub")
    shared = ours[start:end].rstrip()
    assert shared in theirs


def test_margin_control_rounds_instead_of_truncating(tmp_path, data_dir):
    cfg_file = data_dir / "bac-pricing-config.toml"
    cfg_file.write_text(
        cfg_file.read_text().replace("target_margin           = 0.2\n", "target_margin           = 0.29\n")
    )
    defs = run_notebook(write_files_config(tmp_path, data_dir))
    assert defs["model"].cfg["financials"]["target_margin"] == pytest.approx(0.29)


def test_tier_controls_bind_by_kind_not_label(tmp_path, data_dir):
    cfg_file = data_dir / "bac-pricing-config.toml"
    cfg_file.write_text(
        cfg_file.read_text()
        .replace('label = "Education"', 'label = "Schools"')
        .replace('label = "Nonprofit"', 'label = "Clubs"')
    )
    defs = run_notebook(write_files_config(tmp_path, data_dir))
    tiers = {t["label"]: t for t in defs["model"].cfg["discount_tiers"]}
    assert tiers["Schools"]["units"] == 5 and tiers["Clubs"]["units"] == 5
    assert defs["pr"].price_rounded == 1138.0


def test_resolve_carries_ref_and_notes_the_editors_do_not_show(tmp_path):
    defs = run_notebook(write_files_config(tmp_path, FIXTURES))
    assert sum(1 for e in defs["model"].edges if e["notes"]) == 11
    assert defs["model"].edges[0]["ref"] == ""
