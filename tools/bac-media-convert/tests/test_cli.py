# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
from pathlib import Path

from bac_media_convert import __version__, cli, video
from media_testkit import make_image
from PIL import Image

from bac_common.testing import invoke

TOOL = "bac-media-convert"


def _help_lines(*argv: str) -> list[str]:
    r = invoke(cli._main, [*argv, "--help"])
    assert r.exit_code == 0, r.output
    assert "--debug" not in r.stdout
    return r.stdout.rstrip().splitlines()


def test_version_and_help_lengths():
    r = invoke(cli._main, ["-v"])
    assert r.exit_code == 0 and r.stdout.strip() == f"{TOOL} v{__version__}"
    for argv in ((), ("webp-square",), ("cfr",)):
        lines = _help_lines(*argv)
        assert len(lines) <= 24, "\n".join(lines)
    assert "Build a CubeSat" in "\n".join(_help_lines())
    r = invoke(cli._main, [])
    assert r.exit_code == 0 and "Examples:" in r.stdout


def test_webp_square_folder(photos):
    r = invoke(cli._main, ["webp-square", str(photos)])
    assert r.exit_code == 0, r.output
    for name, side in (("wide.webp", 300), ("tall.webp", 200), ("small.webp", 40)):
        with Image.open(photos / name) as img:
            assert img.size == (side, side) and img.format == "WEBP"
    assert not (photos / "notes.webp").exists()
    assert r.stdout.count("✓") == 3 and "300×300" in r.stdout
    assert not list(photos.glob("*.part.*"))
    assert "Inputs" in r.stdout and "Converted  :  3" in r.stdout.replace(" ", " ")


def test_webp_square_skips_existing_unless_force(photos):
    (photos / "wide.webp").write_bytes(b"keep me")
    r = invoke(cli._main, ["webp-square", str(photos)])
    assert r.exit_code == 0, r.output
    assert "! Skipped" in r.stdout and "wide.webp" in r.stdout and "--force" in r.stdout
    assert (photos / "wide.webp").read_bytes() == b"keep me"
    assert "Skipped    :  1" in r.stdout

    r = invoke(cli._main, ["webp-square", str(photos / "wide.jpg"), "--force"])
    assert r.exit_code == 0, r.output
    with Image.open(photos / "wide.webp") as img:
        assert img.format == "WEBP"


def test_webp_square_out_dir_max_side_and_dry_run(photos, tmp_path):
    out = tmp_path / "out" / "webp"
    r = invoke(cli._main, ["webp-square", str(photos), "--out-dir", str(out), "--max-side", "100", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "Would write" in r.stdout and "dry run – no changes made" in r.stdout
    assert not out.exists()

    r = invoke(cli._main, ["webp-square", str(photos), "--out-dir", str(out), "--max-side", "100"])
    assert r.exit_code == 0, r.output
    with Image.open(out / "wide.webp") as img:
        assert img.size == (100, 100)
    with Image.open(out / "small.webp") as img:
        assert img.size == (40, 40)  # never upscaled


def test_webp_square_collision_is_an_error(tmp_path):
    make_image(tmp_path / "a.jpg", (4, 4))
    make_image(tmp_path / "a.png", (4, 4))
    r = invoke(cli._main, ["webp-square", str(tmp_path)])
    assert r.exit_code == 2
    assert "same output file" in r.stderr and "a.jpg and a.png" in r.stderr
    assert not (tmp_path / "a.webp").exists()


def test_webp_square_unreadable_file_fails_that_file_only(photos):
    bad = photos / "broken.jpg"
    bad.write_bytes(b"not a jpeg")
    r = invoke(cli._main, ["webp-square", str(photos)])
    assert r.exit_code == 1
    assert "✗" in r.stdout and "broken.jpg" in r.stdout
    assert (photos / "wide.webp").exists() and not (photos / "broken.webp").exists()
    assert "Failed     :  1" in r.stdout


def test_usage_errors(tmp_path, photos):
    for argv in (
        ["webp-square", str(tmp_path / "nope")],
        ["webp-square", str(photos), "--quality", "0"],
        ["cfr", str(photos), "--crf", "99"],
        ["webp-square"],
    ):
        r = invoke(cli._main, argv)
        assert r.exit_code == 2, (argv, r.output)
        assert "Traceback" not in r.stderr
    (tmp_path / "empty").mkdir()
    r = invoke(cli._main, ["webp-square", str(tmp_path / "empty")])
    assert r.exit_code == 1 and "No input files" in r.stderr


def test_cfr_builds_commands_and_mocks_ffmpeg(tmp_path, monkeypatch):
    clips = tmp_path / "clips"
    clips.mkdir()
    for name in ("b.webm", "a.mkv", "skip.txt"):
        (clips / name).write_bytes(b"x")
    (clips / "a_30fps.mp4").write_bytes(b"old")
    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        assert kwargs["stdin"] is subprocess.DEVNULL and kwargs["errors"] == "replace"
        Path(cmd[-1]).write_bytes(b"\0" * 2048)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")

    r = invoke(cli._main, ["cfr", str(clips), "--fps", "30", "--crf", "20"])
    assert r.exit_code == 0, r.output
    assert len(commands) == 1 and commands[0] == video.cfr_command(
        clips / "b.webm", clips / "b_30fps.part.mp4", fps=30, crf=20, ffmpeg="/usr/bin/ffmpeg"
    )
    assert (clips / "b_30fps.mp4").stat().st_size == 2048 and not (clips / "b_30fps.part.mp4").exists()
    assert "! Skipped" in r.stdout and "a_30fps.mp4" in r.stdout
    assert (clips / "a_30fps.mp4").read_bytes() == b"old"
    assert "✓" in r.stdout and "b_30fps.mp4" in r.stdout
    assert "a_30fps_30fps" not in r.stdout  # earlier outputs in the folder are not re-encoded

    r = invoke(cli._main, ["cfr", str(clips / "a.mkv"), "--fps", "30", "--force", "--out-dir", str(tmp_path / "o")])
    assert r.exit_code == 0, r.output
    assert commands[-1][-1] == str(tmp_path / "o" / "a_30fps.part.mp4")
    assert (tmp_path / "o" / "a_30fps.mp4").exists()


def test_cfr_without_ffmpeg(tmp_path, monkeypatch):
    (tmp_path / "c.webm").write_bytes(b"x")
    monkeypatch.setattr("shutil.which", lambda name: None)
    r = invoke(cli._main, ["cfr", str(tmp_path / "c.webm")])
    assert r.exit_code == 1 and "ERROR ffmpeg is not installed" in r.stderr
    r = invoke(cli._main, ["cfr", str(tmp_path / "c.webm"), "--dry-run"])
    assert r.exit_code == 0 and "Would write" in r.stdout and "! ffmpeg is not installed" in r.stdout


def test_cfr_reports_ffmpeg_failure(tmp_path, monkeypatch):
    (tmp_path / "c.webm").write_bytes(b"x")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "", "Invalid data found\n")
    )
    r = invoke(cli._main, ["cfr", str(tmp_path / "c.webm")])
    assert r.exit_code == 1
    assert "✗" in r.stdout and "ffmpeg failed (exit 1) for c.webm" in r.stdout and "Invalid data found" in r.stdout
    assert "Failed     :  1" in r.stdout
    assert not (tmp_path / "c_25fps.mp4").exists() and not (tmp_path / "c_25fps.part.mp4").exists()


def test_interrupt_leaves_no_partial_output(photos, monkeypatch):
    def boom(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr("bac_media_convert.webp.convert_square_webp", boom)
    r = invoke(cli._main, ["webp-square", str(photos / "wide.jpg")])
    assert r.exit_code == 1 and "Interrupted" in r.stdout
    assert not (photos / "wide.webp").exists() and not (photos / "wide.part.webp").exists()


def test_own_input_skip_has_no_force_hint(tmp_path):
    src = make_image(tmp_path / "a.webp", (4, 4))
    r = invoke(cli._main, ["webp-square", str(src), "--force"])
    assert r.exit_code == 0 and "own input" in r.stdout and "--force to redo" not in r.stdout
