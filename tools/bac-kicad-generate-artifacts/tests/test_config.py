# SPDX-License-Identifier: MIT
from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path

import pytest
from bac_kicad_generate_artifacts.config import BOM_FIELDS, Settings, config_template, find_ibom_script, load_settings
from bac_kicad_generate_artifacts.stages import STAGE_NAMES, select_stages

from bac_common.errors import ConfigError


def test_defaults_without_a_file(no_config):
    s = load_settings(None)
    assert s == Settings()
    assert s.output_root is None and s.prefix == "bac" and s.qr_marker == "QR_MARKER" and s.source is None
    assert s.bom_fields == BOM_FIELDS and s.ibom_script is None


def test_template_is_valid_toml_and_loads_back(tmp_path: Path):
    text = config_template(Path("/opt/ibom/generate_interactive_bom.py"), today=date(2026, 10, 6))
    data = tomllib.loads(text)
    assert set(data) == {"output", "naming", "metadata", "bom", "ibom", "qr"}
    assert "written by --init on 2026-10-06" in text
    cfg = tmp_path / "c.toml"
    cfg.write_text(text)
    s = load_settings(cfg)
    assert s == Settings(ibom_script=Path("/opt/ibom/generate_interactive_bom.py"))
    assert s.source == cfg


def test_values_are_read(tmp_path: Path):
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[output]\nroot = "~/releases"\ntimeout_s = 30\n[naming]\nprefix = "-acme-"\nhardware_root = "hw"\n'
        '[bom]\nfields = "Reference,Value"\n[ibom]\npython = "/usr/bin/python3"\n[qr]\nmarker = "QR"\ntext = "x"\n'
    )
    s = load_settings(cfg)
    assert s.output_root == Path("~/releases").expanduser() and s.timeout == 30.0
    assert s.prefix == "acme" and s.hardware_root == "hw" and s.bom_fields == "Reference,Value"
    assert s.ibom_python == "/usr/bin/python3" and s.qr_marker == "QR" and s.qr_text == "x"


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("[output]\nroot = 3\n", "root"),
        ("[output]\ntimeout_s = -1\n", "timeout_s"),
        ("naming = 1\n", "table"),
        ("[qr]\nmarker = [1]\n", "marker"),
    ],
)
def test_bad_values(tmp_path: Path, text, match):
    cfg = tmp_path / "c.toml"
    cfg.write_text(text)
    with pytest.raises(ConfigError, match=match):
        load_settings(cfg)


def test_missing_explicit_config_is_an_error(tmp_path: Path):
    with pytest.raises(ConfigError, match="does not exist"):
        load_settings(tmp_path / "nope.toml")


def test_find_ibom_script_prefers_the_newest_kicad(no_config, tmp_path: Path):
    assert find_ibom_script() is None
    for version in ("9.0", "10.0"):
        p = (
            tmp_path
            / f"home/.local/share/kicad/{version}/3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom/generate_interactive_bom.py"
        )
        p.parent.mkdir(parents=True)
        p.write_text("#")
    assert "10.0" in str(find_ibom_script())


def test_stage_selection():
    names = [s.name for s in select_stages(set(), set(), ibom=False, qr=False)]
    assert names == ["render", "schematic", "pinout", "bom", "gerbers", "drills", "centroid", "step", "zip"]
    names = [s.name for s in select_stages(set(), set(), ibom=True, qr=True)]
    assert names == list(STAGE_NAMES) and names[0] == "qr" and names[-1] == "zip"
    assert [s.name for s in select_stages({"ibom"}, set(), ibom=False, qr=False)] == ["ibom"]
    assert [s.name for s in select_stages(set(), {"step", "zip"}, ibom=False, qr=False)][-1] == "centroid"
    assert select_stages({"render"}, {"render"}, ibom=False, qr=False) == []
