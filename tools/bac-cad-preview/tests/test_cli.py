# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import numpy as np
from bac_cad_preview import __version__, cli
from bac_cad_preview.cli import check_collisions, output_path
from PIL import Image

from bac_common.errors import UsageError
from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-cad-preview"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_help_names_the_letter_faces_and_hides_debug():
    r = invoke(cli._main, ["--help"])
    assert r.exit_code == 0
    assert "auto, xp, xm, yp, ym, zp, zm" in r.stdout
    assert "--dry-run" in r.stdout and "--debug" not in r.stdout


def test_output_path():
    assert output_path(Path("a/b/part.step"), None) == Path("a/b/part.webp")
    assert output_path(Path("a/b/part.step"), Path("out")) == Path("out/part.webp")


def test_collision_is_refused_before_any_work(tmp_path):
    a = tmp_path / "part.stl"
    b = tmp_path / "part.step"
    a.write_bytes(b"")
    b.write_bytes(b"")
    try:
        check_collisions([a, b], None)
    except UsageError as e:
        assert "part.webp" in e.message
    else:  # pragma: no cover
        raise AssertionError("two inputs mapping to one output must raise UsageError")
    check_collisions([a, a], None)  # the same file twice is not a collision
    check_collisions([a, tmp_path / "part.txt"], None)  # an unsupported file is skipped later, not a collision
    r = invoke(cli._main, [str(a), str(b)])
    assert r.exit_code == 2
    assert "part.webp" in r.stderr
    assert "Loaded" not in r.stdout


def test_out_dir_must_be_a_directory(box_stl):
    r = invoke(cli._main, [str(box_stl), "--out-dir", str(box_stl)])
    assert r.exit_code == 2
    assert "not a directory" in r.stderr


def test_dry_run_writes_nothing(box_stl):
    out_dir = box_stl.parent / "out"
    r = invoke(cli._main, [str(box_stl), "--out-dir", str(out_dir), "--dry-run"])
    assert r.exit_code == 0, r.output
    assert not out_dir.exists()
    assert "dry run" in r.stdout and "Planned" in r.stdout
    assert "face auto" in r.stdout


def test_render_stl_end_to_end(box_stl):
    out_dir = box_stl.parent / "out"
    r = invoke(cli._main, [str(box_stl), "--out-dir", str(out_dir), "--gizmo-unit", "10", "--face", "top"])
    assert r.exit_code == 0, r.output
    dst = out_dir / "box.webp"
    assert dst.is_file()
    assert "face zp" in r.stdout  # the kicad-cli alias is normalised to the letter form
    with Image.open(dst) as im:
        assert im.size == (720, 720) and im.mode == "RGBA"
        alpha = np.asarray(im)[:, :, 3]
    assert alpha.max() == 255 and alpha[0, 0] == 0
    # second run overwrites in place and says so
    r = invoke(cli._main, [str(box_stl), "--out-dir", str(out_dir), "--no-gizmo", "--no-edges"])
    assert r.exit_code == 0, r.output
    assert "overwritten" in r.stdout


def test_flat_part_turns_its_thin_axis_toward_the_viewer(box_stl):
    """The 40 × 25 × 3 mm box is flat, so auto picks zp and the log says so."""
    out_dir = box_stl.parent / "out"
    r = invoke(cli._main, [str(box_stl), "--out-dir", str(out_dir), "--no-gizmo", "--no-edges"])
    assert r.exit_code == 0, r.output
    assert "flat part: zp faces the viewer" in r.stdout
    assert "face zp auto" in r.stdout


def test_mesh_default_is_rbf_red(box_stl):
    out_dir = box_stl.parent / "out"
    r = invoke(cli._main, [str(box_stl), "--out-dir", str(out_dir), "--no-gizmo", "--no-edges"])
    assert r.exit_code == 0, r.output
    assert "RBF red" in r.stdout
    with Image.open(out_dir / "box.webp") as im:
        px = np.asarray(im)
    covered = px[:, :, 3] == 255
    rgb = px[covered][:, :3].astype(int)
    assert (rgb[:, 0] > rgb[:, 1] + 40).all() and (rgb[:, 0] > rgb[:, 2] + 40).all()  # red dominates everywhere


def test_example_bracket_renders(tmp_path):
    r = invoke(cli._main, [str(EXAMPLES / "bracket.stl"), "--out-dir", str(tmp_path), "--no-edges"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "bracket.webp").is_file()
    assert "face ym auto" in r.stdout  # the bracket is not flat: Z up, FreeCAD orientation


def test_missing_and_unsupported_files(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("x")
    r = invoke(cli._main, [str(tmp_path / "missing.stl")])
    assert r.exit_code == 1
    assert "not found" in r.stdout
    r = invoke(cli._main, [str(other)])
    assert r.exit_code == 0  # skipped, not failed
    assert "skipped" in r.stdout


def test_one_bad_file_does_not_end_the_batch(box_stl, tmp_path):
    """An unreadable file prints its ✗ line; the good file is still rendered; exit 1; the summary is printed."""
    broken = tmp_path / "broken.stl"
    broken.write_bytes(b"")
    out_dir = tmp_path / "out"
    r = invoke(cli._main, [str(broken), str(box_stl), "--out-dir", str(out_dir), "--no-gizmo", "--no-edges", "--debug"])
    assert r.exit_code == 1, r.output
    assert "✗" in r.stdout and "broken.stl" in r.stdout
    assert (out_dir / "box.webp").is_file()
    assert "Failed" in r.stdout and "Rendered" in r.stdout


def test_bad_options_exit_2(box_stl):
    for argv in (
        ["--rotate", "1,2"],
        ["--face", "w"],
        ["--flat-ratio", "0.5"],
        ["--color", "red"],
        ["--gizmo-unit", "0"],
        ["--deflection", "-1"],
    ):
        r = invoke(cli._main, [str(box_stl), *argv])
        assert r.exit_code == 2, argv
        assert "ERROR" in r.stderr, argv
