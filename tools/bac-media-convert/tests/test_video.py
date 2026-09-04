# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from bac_media_convert import video

from bac_common.errors import ExternalToolError


def test_target_name_and_own_output():
    assert video.target_name(Path("x/clip.webm")) == "clip_25fps.mp4"
    assert video.target_name(Path("clip.mov"), fps=30) == "clip_30fps.mp4"
    assert video.is_own_output(Path("clip_25fps.mp4")) and video.is_own_output(Path("x/Clip_60FPS.MP4"))
    assert not video.is_own_output(Path("clip.mp4")) and not video.is_own_output(Path("_25fps.mp4"))


def test_cfr_command_is_an_argv_list():
    cmd = video.cfr_command(Path("in put.webm"), Path("out/in put_25fps.mp4"), fps=25, crf=18, ffmpeg="/usr/bin/ffmpeg")
    assert cmd[0] == "/usr/bin/ffmpeg" and cmd[-1] == "out/in put_25fps.mp4"
    assert cmd[cmd.index("-i") + 1] == "in put.webm"
    assert "-n" in cmd and "-vsync" not in cmd
    assert cmd[cmd.index("-vf") + 1] == "crop=trunc(iw/2)*2:trunc(ih/2)*2"
    assert cmd[cmd.index("-r") + 1] == "25" and cmd[cmd.index("-fps_mode") + 1] == "cfr"
    assert cmd[cmd.index("-c:v") + 1] == "libx264" and cmd[cmd.index("-preset") + 1] == "veryfast"
    assert cmd[cmd.index("-crf") + 1] == "18" and cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    other = video.cfr_command(Path("a.webm"), Path("b.mp4"), fps=30, crf=20)
    assert other[other.index("-r") + 1] == "30" and other[other.index("-crf") + 1] == "20" and other[0] == "ffmpeg"


def test_require_ffmpeg(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(ExternalToolError, match="ffmpeg is not installed"):
        video.require_ffmpeg()
    monkeypatch.setattr("shutil.which", lambda name: "/opt/ffmpeg")
    assert video.require_ffmpeg() == "/opt/ffmpeg"


def test_run_ffmpeg_reports_failure_tail(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "warning: x\nError: could not find codec\n\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ExternalToolError) as info:
        video.run_ffmpeg(["ffmpeg", "-i", "clip.webm", "out.mp4"], "clip.webm")
    assert info.value.message == "ffmpeg failed (exit 1) for clip.webm"
    assert info.value.detail == "warning: x · Error: could not find codec"
    assert calls == [["ffmpeg", "-i", "clip.webm", "out.mp4"]]

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""))
    video.run_ffmpeg(["ffmpeg"], "x")  # no error


def test_run_ffmpeg_missing_binary(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(ExternalToolError, match="Could not start ffmpeg"):
        video.run_ffmpeg(["ffmpeg"])
