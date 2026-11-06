# SPDX-License-Identifier: MIT
"""The catalog check: the folders found, the findings, the README tables regenerated."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from bac_kicad_maintain import cli
from bac_kicad_maintain.catalogs import inspect

from bac_common.errors import ConfigError
from bac_common.testing import invoke

FIXTURE = Path(__file__).resolve().parents[3] / "lib" / "bac-common" / "tests" / "catalog"

README = """# ICs

## 1. Files

x

## 3. Slots

stale

## 4. Catalog

Every slot, one table each.

stale

## 5. Column reference

| a |

## 8. Version history

| Version | Date | Change |
| --- | --- | --- |
| v0.9.1 | 2026-11-05 | test |
"""


def make_root(tmp_path: Path, *, readme: bool = True) -> Path:
    root = tmp_path / "hw"
    catalog = root / "resources" / "catalog"
    for name in ("passives", "ics", "other"):
        shutil.copytree(FIXTURE / name, catalog / name)
    if readme:
        (catalog / "ics" / "README.md").write_text(README)
        (catalog / "other" / "README.md").write_text("# Other\n\nNo tables here.\n")
    return root


def test_inspect_finds_the_folders_by_their_files(tmp_path):
    root = make_root(tmp_path)
    report = inspect(
        root, [Path("resources/catalog/passives"), Path("resources/catalog/ics"), Path("resources/catalog/other")]
    )
    assert (
        set(report.folders) == {"passives", "ics", "other"}
        and report.catalog.counts() == "15 passives, 15 ICs, 7 other"
    )
    assert report.catalog.versions == {"passives": "", "ics": "0.9.1", "other": ""}
    assert report.findings == [] and [p.path.name for p in report.readmes] == ["README.md"]
    assert report.readmes[0].path.parent.name == "ics" and "## 3. Slots\n\n| Slot |" in report.readmes[0].text
    assert [p.parent.name for p in report.plain] == ["other"] and report.notes == []
    report = inspect(root, [Path("resources/catalog/ics")])
    assert set(report.folders) == {"ics"} and report.notes == []
    with pytest.raises(ConfigError, match="No catalog folder found"):
        inspect(root, [Path("nowhere")])


def test_check_reports_and_apply_rewrites(tmp_path):
    root = make_root(tmp_path)
    r = invoke(cli._main, ["check", str(root), "--catalog"])
    assert r.exit_code == 1, r.output
    assert "15 passives, 15 ICs, 7 other" in r.stdout and "passives: no version history" in r.stdout
    assert "resources/catalog/other/README.md has no generated sections" in r.stdout
    assert "stale README tables (1)" in r.stdout and "resources/catalog/ics/README.md" in r.stdout
    assert "Catalog findings     :  0" in r.stdout and "Stale README tables  :  1" in r.stdout
    r = invoke(cli._main, ["check", str(root), "--catalog", "--diff"])
    assert r.exit_code == 1 and "-stale" in r.stdout and "+| `can-xcvr-sot23-8` |" in r.stdout

    r = invoke(cli._main, ["apply", str(root), "--catalog", "--dry-run"])
    assert r.exit_code == 0 and (root / "resources/catalog/ics/README.md").read_text() == README
    r = invoke(cli._main, ["apply", str(root), "--catalog", "--yes"])
    assert r.exit_code == 0, r.output
    assert "✓ Wrote resources/catalog/ics/README.md" in r.stdout and "Files written        :  1" in r.stdout
    text = (root / "resources/catalog/ics/README.md").read_text()
    assert (root / "resources/catalog/ics/README.md.bak").read_text() == README
    assert text.startswith("# ICs\n\n## 1. Files\n\nx\n\n## 3. Slots\n\n| Slot | Function |")
    assert "Every slot, one table each." in text and text.endswith("| v0.9.1 | 2026-11-05 | test |\n")
    assert "### `mcu-lqfp64` – " in text and "stale" not in text
    r = invoke(cli._main, ["check", str(root), "--catalog"])
    assert r.exit_code == 0 and "nothing" not in r.stdout
    r = invoke(cli._main, ["apply", str(root), "--catalog", "--yes"])
    assert r.exit_code == 0 and "nothing to rewrite" in r.stdout


def test_findings_exit_1_and_show_in_json(tmp_path):
    root = make_root(tmp_path)
    ics = root / "resources/catalog/ics/bac-ics.csv"
    lines = ics.read_text().splitlines()
    lines[1] = lines[1].replace("industrial", "military", 1)
    ics.write_text("\n".join(lines) + "\n")
    r = invoke(cli._main, ["check", str(root), "--catalog"])
    assert r.exit_code == 1 and "catalog findings (1)" in r.stdout and "qualification 'military'" in r.stdout
    r = invoke(cli._main, ["check", str(root), "--catalog", "--json"])
    data = json.loads(r.stdout)
    assert data["catalog"] and data["counts"] == {"passives": 15, "ics": 15, "other": 7}
    assert data["findings"][0]["row"] == "can-xcvr-sot23-8.tcan334g" and data["versions"]["ics"] == "0.9.1"
    assert data["stale_readmes"] == [str(root / "resources/catalog/ics/README.md")]
    assert data["plain_readmes"] == [str(root / "resources/catalog/other/README.md")]


def test_catalog_usage_errors(tmp_path):
    root = make_root(tmp_path)
    r = invoke(cli._main, ["check", str(root), "--catalog", "--audit"])
    assert r.exit_code == 2 and "runs on its own" in r.stderr
    r = invoke(cli._main, ["check", str(root), "--catalog", "--text"])
    assert r.exit_code == 2 and "--catalog runs on its own" in r.stderr
    r = invoke(cli._main, ["check", str(root / "resources"), str(root), "--catalog"])
    assert r.exit_code == 2 and "one directory" in r.stderr
    r = invoke(cli._main, ["check", str(root), "--catalog", "--exclude", "x"])
    assert r.exit_code == 2 and "--exclude does not apply" in r.stderr
    r = invoke(cli._main, ["apply", str(root), "--catalog", "--json"])
    assert r.exit_code == 2 and "--json writes only with --yes" in r.stderr
    r = invoke(cli._main, ["check", str(tmp_path), "--catalog"])
    assert r.exit_code == 1 and "No catalog folder found" in r.stderr
    cfg = tmp_path / "m.toml"
    cfg.write_text('[audit]\ncatalogs = ["resources/catalog/ics"]\n')
    r = invoke(cli._main, ["--config", str(cfg), "check", str(root), "--catalog"])
    assert r.exit_code == 1 and "15 ICs" in r.stdout and "passives" not in r.stdout.split("Checking")[1][:200]
