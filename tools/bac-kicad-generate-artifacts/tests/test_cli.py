# SPDX-License-Identifier: MIT
"""The command line end to end, with kicad-cli replaced by the fake runner."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from bac_kicad_generate_artifacts import __version__, cli
from bac_kicad_generate_artifacts.stages import STAGE_NAMES
from PIL import Image

from bac_common.cad import read_step_header
from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-kicad-generate-artifacts"


def test_standard_flags(no_config):
    assert_standard_flags(cli._main, TOOL, __version__)


def test_help_fits_and_names_the_options(no_config):
    r = invoke(cli._main, ["--help"])
    assert r.exit_code == 0
    for word in (
        "--desktop",
        "--only",
        "--skip",
        "--ibom",
        "--qr",
        "--patch",
        "--open",
        "--config",
        "--init",
        "--dry-run",
    ):
        assert word in r.stdout
    assert "--debug" not in r.stdout and "--env-file" not in r.stdout
    assert max(len(line) for line in r.stdout.splitlines()) <= 80


def test_no_folder_is_a_usage_error(no_config):
    r = invoke(cli._main, [])
    assert r.exit_code == 2 and "at least one" in r.stderr


def test_unknown_stage_lists_the_stages(fake, synth):
    r = invoke(cli._main, ["--only", "render,gerber", str(synth)])
    assert r.exit_code == 2
    assert "Unknown stage: gerber" in r.stderr and ", ".join(STAGE_NAMES) in r.stderr


def test_missing_programs_are_named(no_config, monkeypatch, synth):
    # a machine with kicad-cli installed must see the same result: the lookup happens at call time
    monkeypatch.setattr("bac_kicad_generate_artifacts.runner.shutil.which", lambda name: None)
    r = invoke(cli._main, [str(synth)])
    assert r.exit_code == 1 and "kicad-cli" in r.stderr and "rsvg-convert" in r.stderr
    monkeypatch.setattr("bac_kicad_generate_artifacts.runner.shutil.which", lambda name: f"/usr/bin/{name}")
    r = invoke(cli._main, ["--dry-run", "--only", "centroid", str(synth)])
    assert r.exit_code == 0, r.output


def test_relative_output_root_is_made_absolute(fake, synth, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = invoke(cli._main, ["--desktop", "out", "--only", "centroid", str(synth)])
    assert r.exit_code == 0, r.output
    (cmd,) = [c for c in fake.commands if c[1:4] == ["pcb", "export", "pos"]]
    assert cmd[cmd.index("--output") + 1].startswith(str(tmp_path / "out"))
    assert f"Output     {tmp_path / 'out' / 'bac-synth-v2r3'}" in r.stdout


def test_init_writes_the_config_once(no_config, tmp_path):
    plugin = (
        tmp_path
        / "home/.local/share/kicad/10.0/3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom/generate_interactive_bom.py"
    )
    plugin.parent.mkdir(parents=True)
    plugin.write_text("# plugin")
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0, r.output
    path = tmp_path / "config" / f"{TOOL}.toml"
    assert path.is_file() and "Wrote" in r.stdout
    text = path.read_text()
    assert f'script = "{plugin}"' in text and 'prefix = "bac"' in text and "${ITEM_NUMBER}" in text
    assert "[metadata]" in r.stdout and "[ibom]" not in r.stdout  # Rich must not eat the table names as markup
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0 and "left as it is" in r.stdout
    assert path.read_text() == text


def test_dry_run_writes_nothing(fake, synth, tmp_path):
    out = tmp_path / "out"
    cfg = tmp_path / "ga.toml"
    cfg.write_text(f'[ibom]\nscript = "{tmp_path / "plugin.py"}"\n')
    argv = [
        "--dry-run",
        "--qr",
        "https://bac.page/synth",
        "--ibom",
        "--desktop",
        str(out),
        "--config",
        str(cfg),
        str(synth),
    ]
    r = invoke(cli._main, argv)
    assert r.exit_code == 0, r.output
    assert not out.exists()
    assert "dry run" in r.stdout and "Planned" in r.stdout
    assert "· QR code" in r.stdout and "encodes 'https://bac.page/synth'" in r.stdout
    assert "· Render → bac-synth-v2r3-render.webp" in r.stdout
    assert "· iBOM → bac-synth-v2r3-ibom.html" in r.stdout
    assert "· Zip → bac-synth-v2r3-<YYYY-MM-DD-HH-MM>.zip" in r.stdout
    # every kicad-cli call was recorded, none ran
    subs = fake.subcommands()
    assert "pcb render --output" in subs and "pcb export step" in subs and "sch export bom" in subs
    assert not (synth / ".work").exists()


def test_dry_run_validates(fake, synth, tmp_path):
    r = invoke(cli._main, ["--dry-run", "--ibom", "--desktop", str(tmp_path / "o"), str(synth)])
    assert r.exit_code == 1 and "✗ iBOM" in r.stdout and "plugin path" in r.stdout
    assert not (tmp_path / "o").exists()


def test_full_run_on_the_synthetic_project(fake, synth, tmp_path):
    out = tmp_path / "out"
    r = invoke(cli._main, ["--desktop", str(out), "--qr", "${COMMENT4}", str(synth)])
    assert r.exit_code == 0, r.output
    project_dir = out / "bac-synth-v2r3"
    names = sorted(p.name for p in project_dir.iterdir())
    (zip_name,) = [n for n in names if n.endswith(".zip")]
    assert sorted(set(names) - {zip_name}) == [
        "bac-synth-v2r3-bom.csv",
        "bac-synth-v2r3-model.step",
        "bac-synth-v2r3-pinout.webp",
        "bac-synth-v2r3-render.webp",
        "bac-synth-v2r3-schematic.pdf",
        "centroid",
        "drill",
        "gerber",
    ]
    assert re.fullmatch(r"bac-synth-v2r3-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}\.zip", zip_name)
    assert f"✓ Zip → {zip_name}" in r.stdout
    # the QR stage worked on a copy, the project is untouched, the copy is gone
    assert "QR_MARKER" in (synth / "bac-synth-v2.kicad_pcb").read_text()
    assert not (project_dir / ".work").exists()
    assert "2 markers, encodes 'https://bac.page/synth'" in r.stdout
    # the exports came from the copy
    board_args = [c[-1] for c in fake.commands if c[1] == "pcb"]
    assert board_args and all(a.endswith(".work/project/bac-synth-v2.kicad_pcb") for a in board_args)
    sch_args = [c[-1] for c in fake.commands if c[1] == "sch"]
    assert sch_args and all(a == str(synth / "bac-synth-v2.kicad_sch") for a in sch_args)
    # images are 720 px squares and a 1920 × 1080 canvas
    with Image.open(project_dir / "bac-synth-v2r3-render.webp") as im:
        assert im.size == (720, 720) and im.mode == "RGBA"
    with Image.open(project_dir / "bac-synth-v2r3-pinout.webp") as im:
        assert im.size == (1920, 1080)
    # gerbers renamed to the scheme, display names and spaces gone, job file follows
    gerbers = sorted(p.name for p in (project_dir / "gerber").iterdir())
    assert "bac-synth-v2r3-In1_Cu.gbr" in gerbers and "bac-synth-v2r3-F_Silkscreen.gbr" in gerbers
    assert not any(" " in g for g in gerbers) and "bac-synth-v2r3-job.gbrjob" in gerbers
    job = json.loads((project_dir / "gerber" / "bac-synth-v2r3-job.gbrjob").read_text())
    assert all(f["Path"] in gerbers for f in job["FilesAttributes"])
    assert [p.name for p in (project_dir / "drill").iterdir()] == ["bac-synth-v2r3.drl"]
    with zipfile.ZipFile(project_dir / zip_name) as zf:
        members = zf.namelist()
    assert "gerber/bac-synth-v2r3-F_Cu.gbr" in members and "drill/bac-synth-v2r3.drl" in members
    assert "centroid/bac-synth-v2r3-centroid.pos" in members and len(members) == len(gerbers) + 2
    # the STEP header got its name
    assert read_step_header(project_dir / "bac-synth-v2r3-model.step").name == "bac-synth-v2r3-model.step"
    # four copper layers plus the fixed set, no User.Comments, zone fills as saved
    (gerber_cmd,) = [c for c in fake.commands if c[1:4] == ["pcb", "export", "gerbers"]]
    layers = gerber_cmd[gerber_cmd.index("--layers") + 1].split(",")
    assert layers[:4] == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] and "User.Comments" not in layers
    assert "--check-zones" not in gerber_cmd
    assert "✓ Render" in r.stdout and "✓ Zip" in r.stdout and "Done" in r.stdout
    assert "iBOM" not in r.stdout  # opt-in, not asked for


def test_config_drives_prefix_metadata_and_qr(fake, synth, tmp_path):
    cfg = tmp_path / "ga.toml"
    cfg.write_text(
        f'[output]\nroot = "{tmp_path / "root"}"\n[naming]\nprefix = "acme"\nhardware_root = "hw"\n'
        '[metadata]\nauthor = "Mänu"\norganization = "Build a CubeSat"\n[qr]\ntext = "https://bac.page/${REVISION}"\n'
    )
    r = invoke(cli._main, ["--config", str(cfg), str(synth)])
    assert r.exit_code == 0, r.output
    # the prefix is not "bac", so the stem's bac- stays part of the name
    project_dir = tmp_path / "root" / "acme-eps-bac-synth-v2r3"
    assert (project_dir / "acme-eps-bac-synth-v2r3-render.webp").is_file()
    header = read_step_header(project_dir / "acme-eps-bac-synth-v2r3-model.step")
    assert header.author == ["Mänu"] and header.organization == ["Build a CubeSat"]
    assert "encodes 'https://bac.page/3'" in r.stdout
    assert f"config {cfg}" in r.stdout
    assert "Mänu, Build a CubeSat" in r.stdout


def test_panel_skips_the_schematic_stages(fake, panel, tmp_path):
    out = tmp_path / "out"
    r = invoke(cli._main, ["--desktop", str(out), str(panel)])
    assert r.exit_code == 0, r.output
    assert "a panel" in r.stdout
    for label in ("Schematic", "Pinout", "BOM"):
        assert f"· {label} – skipped (panel)" in r.stdout
    assert "✓ Render" in r.stdout and "✓ Gerbers" in r.stdout
    (gerber_cmd,) = [c for c in fake.commands if c[1:4] == ["pcb", "export", "gerbers"]]
    assert gerber_cmd[gerber_cmd.index("--layers") + 1].endswith(",Edge.Cuts,User.Comments")
    assert not any(c[1] == "sch" for c in fake.commands)
    names = sorted(p.name for p in (out / "bac-synth-panel-v1r1").iterdir())
    assert "bac-synth-panel-v1r1-render.webp" in names and not any("bom" in n or "schematic" in n for n in names)


def test_ibom_stage(fake, synth, tmp_path):
    cfg = tmp_path / "ga.toml"
    plugin = tmp_path / "generate_interactive_bom.py"
    plugin.write_text("# plugin")
    cfg.write_text(f'[ibom]\nscript = "{plugin}"\npython = "/opt/kicad/python3"\n')
    r = invoke(cli._main, ["--config", str(cfg), "--desktop", str(tmp_path / "o"), "--only", "ibom", str(synth)])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "o" / "bac-synth-v2r3" / "bac-synth-v2r3-ibom.html").is_file()
    probe = [c for c in fake.commands if c[1:3] == ["-c", "import pcbnew"]]
    assert probe[0][0] == "/opt/kicad/python3"  # the configured interpreter is probed first
    (ibom_cmd,) = [c for c in fake.commands if str(plugin) in c]
    assert ibom_cmd[0] == "/opt/kicad/python3" and "--dark-mode" in ibom_cmd
    # the plugin resolves --dest-dir against the board's folder: both paths must be absolute
    assert Path(ibom_cmd[ibom_cmd.index("--dest-dir") + 1]).is_absolute()
    assert Path(ibom_cmd[ibom_cmd.index("--netlist-file") + 1]).is_absolute()
    assert any(c[1:4] == ["sch", "export", "netlist"] and "kicadxml" in c for c in fake.commands)


def test_ibom_without_plugin_or_pcbnew(fake, synth, tmp_path):
    r = invoke(cli._main, ["--desktop", str(tmp_path / "o"), "--ibom", "--only", "ibom", str(synth)])
    assert r.exit_code == 1 and "✗ iBOM" in r.stdout and "plugin path" in r.stdout
    cfg = tmp_path / "ga.toml"
    plugin = tmp_path / "generate_interactive_bom.py"
    plugin.write_text("# plugin")
    cfg.write_text(f'[ibom]\nscript = "{plugin}"\n')
    fake.pcbnew = False
    r = invoke(
        cli._main, ["--config", str(cfg), "--desktop", str(tmp_path / "o"), "--ibom", "--only", "ibom", str(synth)]
    )
    assert r.exit_code == 1 and "pcbnew" in r.stdout


def test_only_and_skip(fake, synth, tmp_path):
    r = invoke(cli._main, ["--desktop", str(tmp_path / "o"), "--skip", "step,zip,pinout", str(synth)])
    assert r.exit_code == 0, r.output
    assert "STEP" not in r.stdout and "Zip" not in r.stdout and "Pinout" not in r.stdout
    assert "✓ Render" in r.stdout and "✓ Gerbers" in r.stdout
    fake.commands.clear()
    r = invoke(cli._main, ["--desktop", str(tmp_path / "o2"), "--only", "centroid", str(synth)])
    assert r.exit_code == 0 and fake.subcommands() == ["pcb export pos"]
    r = invoke(cli._main, ["--desktop", str(tmp_path / "o3"), "--only", "render", "--skip", "render", str(synth)])
    assert r.exit_code == 0 and "No stages selected" in r.stdout


def test_a_failing_stage_marks_the_project_and_the_run_continues(fake, synth, tmp_path):
    fake.fail = {"pcb export step"}
    out = tmp_path / "o"
    r = invoke(cli._main, ["--desktop", str(out), str(synth)])
    assert r.exit_code == 1
    assert "✗ STEP → bac-synth-v2r3-model.step: kicad-cli failed (exit 1): Error: something kicad-cli says" in r.stdout
    assert "✓ Zip" in r.stdout  # later stages still ran
    assert "Failed" in r.stdout and not (out / "bac-synth-v2r3" / ".work").exists()


def test_several_projects_and_a_bad_folder(fake, synth, panel, tmp_path):
    r = invoke(
        cli._main,
        ["--desktop", str(tmp_path / "o"), "--only", "centroid", str(synth), str(tmp_path / "nowhere"), str(panel)],
    )
    assert r.exit_code == 1
    assert r.stdout.count("✓ Centroid") == 2
    assert "Not a directory" in r.stdout
    assert "Projects" in r.stdout and "Failed" in r.stdout


def test_patch_revision(fake, synth, tmp_path):
    r = invoke(cli._main, ["--desktop", str(tmp_path / "o"), "--patch", "1", "--only", "bom,centroid", str(synth)])
    assert r.exit_code == 0, r.output
    d = tmp_path / "o" / "bac-synth-v2r3.1"
    assert (d / "bac-synth-v2r3.1-bom.csv").is_file() and (d / "centroid" / "bac-synth-v2r3.1-centroid.pos").is_file()


def test_debug_keeps_the_work_folder_and_shows_commands(fake, synth, tmp_path):
    r = invoke(cli._main, ["--debug", "--desktop", str(tmp_path / "o"), "--only", "qr,render", "--qr", "x", str(synth)])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "o" / "bac-synth-v2r3" / ".work" / "project" / "bac-synth-v2.kicad_pcb").is_file()
    assert "$ /usr/bin/kicad-cli pcb render" in r.stdout


def test_qr_without_marker_fails_that_stage(fake, dsw, synth, tmp_path, monkeypatch):
    board = synth / "bac-synth-v2.kicad_pcb"
    board.write_text(board.read_text().replace("QR_MARKER", "OTHER"))
    r = invoke(cli._main, ["--desktop", str(tmp_path / "o"), "--qr", "x", "--only", "qr,render", str(synth)])
    assert r.exit_code == 1 and "No QR_MARKER text box" in r.stdout
    # the render still ran, from the original board
    assert any(c[1:3] == ["pcb", "render"] and c[-1] == str(board) for c in fake.commands)


def test_deployment_switch_fixture(fake, dsw, tmp_path):
    out = tmp_path / "o"
    r = invoke(cli._main, ["--desktop", str(out), "--qr", "${COMMENT4}", str(dsw)])
    assert r.exit_code == 0, r.output
    d = out / "bac-deployment-switch-v1r1"
    assert (d / "bac-deployment-switch-v1r1-render.webp").is_file()
    assert "1 marker, encodes 'https://bac.page/dsw-v1'" in r.stdout
    gerbers = sorted(p.name for p in (d / "gerber").iterdir())
    assert "bac-deployment-switch-v1r1-F_Cu.gbr" in gerbers and not any("MIX" in g for g in gerbers)
