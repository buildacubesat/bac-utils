# SPDX-License-Identifier: MIT
"""Single stages against the fake runner, and the image framing."""

from __future__ import annotations

from pathlib import Path

import pytest
from bac_kicad_generate_artifacts.config import Settings
from bac_kicad_generate_artifacts.project import discover, make_plan
from bac_kicad_generate_artifacts.runner import Runner, find_tools
from bac_kicad_generate_artifacts.stages import (
    Context,
    crop_pad_square_resize_rgba,
    stage_gerbers,
    stage_qr,
    stage_render,
    stage_zip,
)
from genart_testkit import TOOLS, FakeRunner
from PIL import Image

from bac_common.errors import ConfigError, ExternalToolError


def _ctx(project_dir: Path, out: Path, runner: Runner, **kw) -> Context:
    settings = Settings(hardware_root="hw")
    plan = make_plan(discover(project_dir), out, prefix="bac", hardware_root="hw")
    return Context(runner, TOOLS, settings, plan, **kw)


def test_framing_crops_pads_and_squares():
    img = Image.new("RGBA", (2000, 1000), (0, 0, 0, 0))
    img.paste((255, 0, 0, 255), (500, 400, 1500, 600))  # 1000 × 200 content
    out = crop_pad_square_resize_rgba(img, 720, 0.10)
    assert out.size == (720, 720) and out.mode == "RGBA"
    alpha = out.getchannel("A")
    bbox = alpha.getbbox()
    # padded content is 1200 × 240 → square 1200 → content spans the full width minus 10 % padding each side
    assert bbox[0] == pytest.approx(60, abs=4) and bbox[2] == pytest.approx(660, abs=4)  # Lanczos softens the edge
    assert (bbox[3] - bbox[1]) == pytest.approx(120, abs=6)
    with pytest.raises(ValueError, match="empty"):
        crop_pad_square_resize_rgba(Image.new("RGBA", (10, 10), (0, 0, 0, 0)))


def test_framing_matches_bac_cad_preview():
    image = pytest.importorskip("bac_cad_preview.image")
    img = Image.new("RGBA", (900, 700), (0, 0, 0, 0))
    img.paste((0, 80, 200, 255), (100, 300, 700, 450))
    ours = crop_pad_square_resize_rgba(img)
    theirs = image.crop_pad_square_resize_rgba(img).image
    assert ours.tobytes() == theirs.tobytes()


def test_find_tools_names_what_is_missing():
    with pytest.raises(ExternalToolError) as e:
        find_tools(which=lambda name: "/usr/bin/kicad-cli" if name == "kicad-cli" else None)
    assert "rsvg-convert" in e.value.message and "kicad-cli" not in e.value.message
    tools = find_tools(which=lambda name: f"/usr/bin/{name}" if name in ("kicad-cli", "inkscape") else None)
    assert tools.raster_is_inkscape


def test_runner_reports_failures(tmp_path: Path):
    r = Runner()
    with pytest.raises(ExternalToolError, match="exit 3"):
        r(["sh", "-c", "echo 'Error: no such board' >&2; exit 3"])
    assert r.ok(["sh", "-c", "exit 0"]) and not r.ok(["sh", "-c", "exit 1"]) and not r.ok(["/nonexistent/program"])
    with pytest.raises(ExternalToolError, match="Program not found"):
        r(["/nonexistent/program"])
    r = Runner(timeout=0.2)
    with pytest.raises(ExternalToolError, match="did not finish"):
        r(["sleep", "2"])
    dry = Runner(dry_run=True)
    assert dry(["anything"]).returncode == 0 and dry.commands == [["anything"]]


def test_render_stage_writes_a_square_webp(synth, tmp_path):
    ctx = _ctx(synth, tmp_path / "o", FakeRunner())
    ctx.plan.out_dir.mkdir(parents=True)
    note = stage_render(ctx)
    assert ctx.plan.render_webp.is_file() and note.endswith("KB")
    with Image.open(ctx.plan.render_webp) as im:
        assert im.size == (720, 720)
    assert not (ctx.plan.work_dir / "render.png").exists()


def test_render_stage_without_output_is_an_error(synth, tmp_path):
    class Silent(FakeRunner):
        def __call__(self, cmd, **kw):
            self.commands.append(cmd)
            import subprocess

            return subprocess.CompletedProcess(cmd, 0, "", "")

    ctx = _ctx(synth, tmp_path / "o", Silent())
    ctx.plan.out_dir.mkdir(parents=True)
    with pytest.raises(ExternalToolError, match="no render"):
        stage_render(ctx)


def test_qr_stage_needs_text_and_works_on_a_copy(synth, tmp_path):
    ctx = _ctx(synth, tmp_path / "o", FakeRunner())
    with pytest.raises(ConfigError, match="text to encode"):
        stage_qr(ctx)
    ctx.qr_text = "${TITLE}"
    assert ctx.board == synth / "bac-synth-v2.kicad_pcb"
    note = stage_qr(ctx)
    assert note == "2 markers, encodes 'bac Synth Board v2'"  # 0.4 mm modules: no warning
    assert ctx.plan.qr_board.is_file() and ctx.board == ctx.plan.qr_board
    assert (
        "QR_MARKER" not in ctx.plan.qr_board.read_text()
        and "QR_MARKER" in (synth / "bac-synth-v2.kicad_pcb").read_text()
    )
    assert (ctx.plan.qr_board.parent / "bac-synth-v2.kicad_pro").is_file()  # the whole project folder travels


def test_qr_stage_warns_about_tiny_modules(dsw, tmp_path):
    ctx = _ctx(dsw, tmp_path / "o", FakeRunner(), qr_text="https://bac.page/dsw-v1")
    note = stage_qr(ctx)
    assert note.startswith("1 marker, encodes 'https://bac.page/dsw-v1', modules 0.13 mm – under")


def test_qr_stage_failure_leaves_no_copy(synth, tmp_path):
    board = synth / "bac-synth-v2.kicad_pcb"
    board.write_text(board.read_text().replace("QR_MARKER", "GONE"))
    ctx = _ctx(synth, tmp_path / "o", FakeRunner(), qr_text="x")
    with pytest.raises(Exception, match="No QR_MARKER"):
        stage_qr(ctx)
    assert not ctx.plan.qr_board.parent.exists() and ctx.board == board


def test_qr_stage_dry_run_only_reports(synth, tmp_path):
    ctx = _ctx(synth, tmp_path / "o", FakeRunner(dry_run=True), qr_text="x")
    assert stage_qr(ctx) == "encodes 'x'" and not (tmp_path / "o").exists()


def test_gerbers_then_zip(synth, tmp_path):
    runner = FakeRunner()
    ctx = _ctx(synth, tmp_path / "o", runner)
    ctx.plan.out_dir.mkdir(parents=True)
    assert stage_gerbers(ctx) == "12 files"  # 11 layers plus the job file
    note = stage_zip(ctx)
    assert note.startswith("12 files") and "renamed 12 gerber · 0 drill" in note
    assert ctx.shown and ctx.shown.startswith("bac-eps-synth-v2r3-") and ctx.shown.endswith(".zip")
    names = sorted(p.name for p in ctx.plan.gerber_dir.iterdir())
    assert names[0].startswith("bac-eps-synth-v2r3-") and all(" " not in n for n in names)
