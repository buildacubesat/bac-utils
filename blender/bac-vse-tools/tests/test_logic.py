# SPDX-License-Identifier: MIT
"""The pure parts of bac-vse-tools, on any Python."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_media_kind_and_listing(logic, tmp_path: Path):
    for name in ("b.MP4", "a.mov", "c.wav", "notes.txt", ".hidden.mp4", "d.MKV"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.mp4").write_bytes(b"")
    assert logic.media_kind(Path("x.MP4")) == "video"
    assert logic.media_kind(Path("x.flac")) == "audio"
    assert logic.media_kind(Path("x.txt")) is None
    assert [p.name for p in logic.list_media(tmp_path)] == ["a.mov", "b.MP4", "c.wav", "d.MKV"]
    for name in ("clip10.mp4", "clip2.mp4", "Clip1.mp4"):
        (tmp_path / name).write_bytes(b"")
    names = [p.name for p in logic.list_media(tmp_path)]
    assert names[3:6] == ["Clip1.mp4", "clip2.mp4", "clip10.mp4"]  # natural order, case-insensitive


def test_min_frames_and_fps_settings(logic):
    assert logic.min_frames(0, 25) == 0
    assert logic.min_frames(5.0, 25) == 125
    assert logic.min_frames(0.01, 25) == 1
    assert logic.fps_settings(25) == (25, 1.0)
    assert logic.fps_settings(29.97) == (30, pytest.approx(1.001, abs=1e-5))
    assert logic.fps_settings(23.976) == (24, pytest.approx(1.001, abs=1e-5))
    assert logic.fps_settings(59.94) == (60, pytest.approx(1.001, abs=1e-5))
    with pytest.raises(ValueError):
        logic.fps_settings(0)


def test_autosave_name(logic):
    assert logic.autosave_name("/x/edit v3.blend", 7, 120) == "edit v3_import_0007_of_0120.blend"
    assert logic.autosave_name("", 1, 2) == "unsaved_import_0001_of_0002.blend"


def test_proxy_artifact_paths(logic):
    src = "/media/shoot/clip.mp4"
    assert logic.proxy_artifact(src, 25) == Path("/media/shoot/BL_proxy/clip.mp4/proxy_25.avi")
    assert logic.proxy_artifact(src, 50, custom_dir="/p", use_custom_dir=True) == Path("/p/clip.mp4/proxy_50.avi")
    assert logic.proxy_artifact(src, 25, custom_dir="/p", use_custom_dir=False).parts[-3] == "BL_proxy"
    assert logic.proxy_artifact(src, 100, storage="PROJECT", project_dir="/all") == Path("/all/clip.mp4/proxy_100.avi")
    # project storage always needs the resolved directory (the caller turns "" into //BL_proxy)
    with pytest.raises(ValueError):
        logic.proxy_artifact(src, 25, storage="PROJECT", project_dir="")


def test_proxy_wait_fresh_file(logic):
    wait = logic.ProxyWait(started=100.0, before_mtime=None, stable_time=2.0, timeout=180.0)
    assert wait.observe(100.5, None) == "waiting"  # not there yet
    assert wait.observe(101.0, 101.0) == "waiting"  # appeared: the clock starts
    assert wait.observe(102.0, 101.9) == "waiting"  # still being written
    assert wait.observe(103.0, 101.9) == "waiting"  # unchanged for 1 s
    assert wait.observe(104.0, 101.9) == "done"  # unchanged for 2 s


def test_proxy_wait_ignores_a_stale_proxy(logic):
    wait = logic.ProxyWait(started=100.0, before_mtime=50.0, stable_time=2.0, timeout=180.0)
    assert wait.observe(101.0, 50.0) == "waiting"  # the old file is not the new build
    assert wait.observe(110.0, 50.0) == "waiting"
    assert wait.observe(111.0, 110.5) == "waiting"
    assert wait.observe(114.0, 110.5) == "done"


def test_proxy_wait_times_out_with_and_without_a_file(logic):
    absent = logic.ProxyWait(started=0.0, before_mtime=None, stable_time=2.0, timeout=10.0)
    assert absent.observe(9.0, None) == "waiting"
    assert absent.observe(10.5, None) == "timeout"
    stale = logic.ProxyWait(started=0.0, before_mtime=1.0, stable_time=2.0, timeout=10.0)
    assert stale.observe(10.5, 1.0) == "timeout"  # the 1.x add-on waited forever here
    changing = logic.ProxyWait(started=0.0, before_mtime=None, stable_time=2.0, timeout=10.0)
    for t in range(1, 10):
        assert changing.observe(float(t), float(t)) == "waiting"
    assert changing.observe(10.5, 10.5) == "timeout"


def test_trim_plan(logic):
    plan = logic.trim_plan(
        20,
        80,
        [
            ("inside", 30, 50),
            ("left", 10, 30),
            ("right", 70, 100),
            ("both", 0, 200),
            ("before", 0, 20),
            ("after", 80, 90),
        ],
    )
    by_name = {p.name: p for p in plan}
    assert by_name["inside"].action == "keep" and (by_name["inside"].start, by_name["inside"].end) == (30, 50)
    assert by_name["left"].action == "clip" and (by_name["left"].start, by_name["left"].end) == (20, 30)
    assert by_name["right"].action == "clip" and (by_name["right"].start, by_name["right"].end) == (70, 80)
    assert by_name["both"].action == "clip" and (by_name["both"].start, by_name["both"].end) == (20, 80)
    assert by_name["before"].action == "remove"  # ends exactly at the meta's start: exclusive end
    assert by_name["after"].action == "remove"
    assert logic.count_actions(plan) == {"keep": 1, "clip": 3, "remove": 2}
    assert logic.trim_plan(0, 10, []) == []
