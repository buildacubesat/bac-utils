# SPDX-License-Identifier: MIT
"""The extension inside Blender's Python (the ``bpy`` module): registration, the three tools' work on a sequencer.

Skipped where ``bpy`` is not importable. What stays untested here is
Blender's event plumbing – the modal timer ticks, the confirm dialogs, the
panels drawing – which needs a window.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest
from vse_testkit import EXTENSION_DIR, add_movies, sequencer_override, strips_of, top_level

pytest.importorskip("bpy")


# -- registration ---------------------------------------------------------------


def test_registration(bpy, extension, scene):
    assert hasattr(bpy.types, "SEQUENCER_OT_bac_bulk_import")
    assert hasattr(bpy.types, "SEQUENCER_OT_bac_sequential_proxies")
    assert hasattr(bpy.types, "SEQUENCER_OT_bac_separate_meta_preserve_trim")
    for panel in ("BAC_PT_vse_bulk_import", "BAC_PT_vse_sequential_proxies", "BAC_PT_vse_strip_utilities"):
        cls = getattr(bpy.types, panel)
        assert cls.bl_category == "VSE Tools" and cls.bl_space_type == "SEQUENCE_EDITOR"
    settings = scene.bac_vse_tools
    assert settings.pause_seconds == pytest.approx(0.1)
    assert settings.retries_per_file == 2 and settings.min_length == pytest.approx(5.0)
    assert settings.autosave is False and settings.autosave_dir == ""
    assert settings.proxy_scope == "CURRENT" and settings.proxy_size == "25" and settings.skip_existing is True
    assert settings.timeout_seconds == 180
    wm = bpy.context.window_manager
    assert hasattr(wm, "bac_vse_bulk_status") and hasattr(wm, "bac_vse_proxy_status")
    for name, prop in settings.bl_rna.properties.items():
        if name in ("rna_type", "name"):
            continue
        assert prop.description and not prop.description.endswith("."), f"{name}: {prop.description!r}"
        assert prop.name == prop.name.strip() and prop.name[0].isupper(), f"{name} display name {prop.name!r}"
    for name in ("stable_time", "check_interval", "timeout_seconds", "pause_seconds", "min_length"):
        assert settings.bl_rna.properties[name].name.endswith("(s)"), name


def test_manifest_matches_the_package():
    import tomllib

    manifest = tomllib.loads((EXTENSION_DIR / "blender_manifest.toml").read_text(encoding="utf-8"))
    assert manifest["id"] == "bac_vse_tools" == EXTENSION_DIR.name
    assert manifest["type"] == "add-on" and manifest["license"] == ["SPDX:MIT"]
    assert manifest["blender_version_min"] == "4.2.0"
    assert len(manifest["tagline"]) <= 64 and not manifest["tagline"].endswith(".")
    assert "files" in manifest["permissions"]
    assert "bl_info =" not in (EXTENSION_DIR / "__init__.py").read_text(encoding="utf-8")


def test_strips_api_fallback_for_blender_42(extension):
    """4.2 and 4.3 have only the ``sequences`` names; the helpers must not touch ``strips`` there."""
    from bac_vse_tools import _common

    class OldSeqed:
        sequences = ["top"]
        sequences_all = ["top", "inner"]

    class OldMeta:
        sequences = ["inner"]

    assert _common.strips(OldSeqed()) == ["top"]
    assert _common.all_strips(OldSeqed()) == ["top", "inner"]
    assert _common.children(OldMeta()) == ["inner"]


# -- bulk import ----------------------------------------------------------------


def run_import(bpy, scene, files, **options):
    from bac_vse_tools.bulk_import import BulkImportRun

    defaults = {"min_length": 0, "retries": 0, "match_fps": True, "autosave_dir": None}
    defaults.update(options)
    run = BulkImportRun(scene, list(files), **defaults)
    results = []
    with sequencer_override(bpy, scene):
        while not run.done:
            results.append(run.step())
    return run, results


def test_bulk_import_sequential_with_filter_and_fps(bpy, extension, scene, clips: Path):
    from bac_vse_tools._logic import list_media

    scene.render.fps = 30
    run, results = run_import(bpy, scene, list_media(clips), min_length=2.5, retries=1)
    assert run.total == 6
    kinds = [k for k, _ in results]
    # clip1, clip2, clip3, clip30, silent, voice
    assert kinds == ["short", "imported", "imported", "imported", "short", "imported"]
    assert (run.imported, run.skipped, run.failed) == (4, 2, 0)
    assert (scene.render.fps, scene.render.fps_base) == (25, 1.0)  # from clip1, even though it was dropped
    assert run.fps_changed == (25, 1.0)

    strips = sorted(strips_of(scene), key=lambda s: (s.frame_final_start, s.channel))
    # Blender's Add Movie names strips after the file, puts the sound on the given channel and the movie above it.
    assert [(s.name.split(".")[0], s.type, s.channel) for s in strips] == [
        ("clip2", "SOUND", 1),
        ("clip2", "MOVIE", 2),
        ("clip3", "SOUND", 1),
        ("clip3", "MOVIE", 2),
        ("clip30", "SOUND", 1),
        ("clip30", "MOVIE", 2),
        ("voice", "SOUND", 1),
    ]
    movies = [s for s in strips if s.type == "MOVIE"]
    sounds = [s for s in strips if s.type == "SOUND"]
    assert movies[0].frame_final_start == 1 and movies[0].frame_final_duration == 100
    assert sounds[0].frame_final_duration == movies[0].frame_final_duration  # in sync at 25 fps
    assert movies[1].frame_final_start == movies[0].frame_final_end + 1
    assert movies[2].frame_final_start == movies[1].frame_final_end + 1
    # the 30 fps clip in the 25 fps scene is retimed, not stretched: 4 s stays 4 s for picture and sound
    assert 99 <= movies[2].frame_final_duration <= 100
    assert sounds[2].frame_final_duration == movies[2].frame_final_duration
    voice = strips[-1]
    assert voice.frame_final_start == movies[2].frame_final_end + 1
    assert 74 <= voice.frame_final_duration <= 76
    assert run.summary() == "Finished: 4 imported, 2 too short, 0 failed"


def test_bulk_import_silent_clip_gets_no_sound_strip_and_keeps_colour_management(bpy, extension, scene, clips):
    view_transform = scene.view_settings.view_transform
    run, results = run_import(bpy, scene, [clips / "silent.mp4"], match_fps=False)
    assert results == [("imported", "24 frames at 1")]  # a 1 s clip at 25 fps, retimed to the 24 fps scene
    assert [s.type for s in strips_of(scene)] == ["MOVIE"]
    assert scene.render.fps == 24  # match_fps off
    assert scene.view_settings.view_transform == view_transform  # set_view_transform=False


def test_bulk_import_appends_after_the_top_level_end(bpy, extension, scene, clips: Path):
    """A strip inside a trimmed meta may run past the meta's end; the next clip starts after the meta, not after it."""
    movies = add_movies(scene, clips, ("clip2", "clip3"))  # 1–101, 102–252
    for s in strips_of(scene):
        s.select = s in movies
    with sequencer_override(bpy, scene):
        bpy.ops.sequencer.meta_make()
    meta = next(s for s in strips_of(scene) if s.type == "META")
    meta.frame_final_end = 150
    run, _ = run_import(bpy, scene, [clips / "clip1.mp4"])
    new_movie = [s for s in strips_of(scene) if s.type == "MOVIE" and s.name.startswith("clip1")][0]
    assert new_movie.frame_final_start == 151
    assert scene.render.fps == 24  # the sequencer was not empty: fps untouched


def test_bulk_import_broken_file_is_failed_after_retries(bpy, extension, scene, tmp_path: Path, capsys):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a movie")
    run, results = run_import(bpy, scene, [broken], retries=2)
    kind, note = results[0]
    assert kind == "failed" and "could not be loaded" in note
    assert run.failed == 1 and strips_of(scene) == []
    assert capsys.readouterr().out.count("attempt") == 3
    assert not any(s.filepath.endswith("broken.mp4") for s in bpy.data.sounds)  # no orphan datablock left
    noise = tmp_path / "noise.wav"
    noise.write_bytes(b"RIFF")
    run, results = run_import(bpy, scene, [noise])
    assert results[0][0] == "failed" and "audio" in results[0][1]


def test_bulk_import_autosave_copies(bpy, extension, scene, clips: Path, tmp_path: Path):
    target = tmp_path / "autosaves"
    run, _ = run_import(bpy, scene, [clips / "clip1.mp4", clips / "voice.mp3"], autosave_dir=target)
    assert sorted(p.name for p in target.iterdir()) == [
        "unsaved_import_0001_of_0002.blend",
        "unsaved_import_0002_of_0002.blend",
    ]
    assert bpy.data.filepath == ""  # a copy was written; the open file is still unsaved
    assert run.autosave_failures == 0


def test_prepare_run_errors_and_the_operator_without_a_folder(bpy, extension, scene, clips: Path, tmp_path: Path):
    from bac_vse_tools.bulk_import import prepare_run

    settings = scene.bac_vse_tools
    assert prepare_run(bpy.context) == (None, "Choose a folder first.")
    with pytest.raises(RuntimeError, match="Choose a folder first"):
        bpy.ops.sequencer.bac_bulk_import()
    settings.import_dir = str(tmp_path / "missing")
    assert prepare_run(bpy.context)[1].startswith("Folder not found")
    empty = tmp_path / "empty"
    empty.mkdir()
    settings.import_dir = str(empty)
    assert prepare_run(bpy.context)[1] == "No video or audio files in that folder."
    settings.import_dir = str(clips)
    settings.autosave = True
    assert prepare_run(bpy.context)[1] == "Autosave is on but no autosave folder is set."
    settings.autosave_dir = str(tmp_path / "saves")
    run, error = prepare_run(bpy.context)
    assert error is None and run.total == 6 and run.autosave_dir == tmp_path / "saves"


# -- sequential proxies ---------------------------------------------------------


def wait_for(path: Path, seconds: float = 60.0) -> None:
    deadline = time.monotonic() + seconds
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert path.is_file(), f"{path} did not appear within {seconds} s"


def test_candidate_strips_scopes_metas_and_duplicates(bpy, extension, scene, clips: Path):
    from bac_vse_tools.sequential_proxies import candidate_strips

    movies = add_movies(scene, clips)
    assert [s.name for s in candidate_strips(scene, "ALL")[0]] == ["clip1", "clip2", "clip3"]
    scene.frame_current = movies[1].frame_final_start
    assert [s.name for s in candidate_strips(scene, "CURRENT")[0]] == ["clip2", "clip3"]
    for s in movies:
        s.select = False
    movies[2].select = True
    assert [s.name for s in candidate_strips(scene, "SELECTED")[0]] == ["clip3"]
    # a second strip on the same file shares the proxy
    top_level(scene.sequence_editor).new_movie("clip1 again", str(clips / "clip1.mp4"), 3, 400)
    names, inside = candidate_strips(scene, "ALL")
    assert [s.name for s in names] == ["clip1", "clip2", "clip3"] and inside == 0
    # a movie inside a meta is left out and counted
    for s in strips_of(scene):
        s.select = s.name == "clip3"
    with sequencer_override(bpy, scene):
        bpy.ops.sequencer.meta_make()
    names, inside = candidate_strips(scene, "ALL")
    assert [s.name for s in names] == ["clip1", "clip2"] and inside == 1


def test_artifact_resolution(bpy, extension, scene, clips: Path, tmp_path: Path):
    from bac_vse_tools.sequential_proxies import artifact_for

    (movie,) = add_movies(scene, clips, ("clip1",))
    seqed = scene.sequence_editor
    movie.use_proxy = True
    assert artifact_for(seqed, movie, 25) == clips / "BL_proxy" / "clip1.mp4" / "proxy_25.avi"
    movie.proxy.use_proxy_custom_directory = True
    movie.proxy.directory = str(tmp_path / "custom")
    assert artifact_for(seqed, movie, 50) == tmp_path / "custom" / "clip1.mp4" / "proxy_50.avi"
    seqed.proxy_storage = "PROJECT"
    seqed.proxy_dir = str(tmp_path / "project")
    assert artifact_for(seqed, movie, 25) == tmp_path / "project" / "clip1.mp4" / "proxy_25.avi"
    seqed.proxy_dir = ""  # Blender's default for project storage: //BL_proxy beside the .blend
    assert artifact_for(seqed, movie, 25).parts[-3:] == ("BL_proxy", "clip1.mp4", "proxy_25.avi")
    assert artifact_for(seqed, movie, 25) == Path(bpy.path.abspath("//BL_proxy")) / "clip1.mp4" / "proxy_25.avi"


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_proxy_run_builds_each_strip_in_turn(bpy, extension, scene, clips: Path, tmp_path: Path):
    from bac_vse_tools.sequential_proxies import ProxyRun

    movies = add_movies(scene, clips, ("clip1", "clip2"))
    movies[0].use_proxy = True
    movies[0].proxy.build_50 = True  # an existing choice the run must keep
    seqed = scene.sequence_editor
    seqed.proxy_storage = "PROJECT"
    seqed.proxy_dir = str(tmp_path / "proxies")
    clock = FakeClock()
    run = ProxyRun(scene, movies, size=25, stable_time=2.0, timeout=60.0, clock=clock)
    with sequencer_override(bpy, scene):
        assert run.tick() == "started"
        artifact = run.artifact
        assert artifact == tmp_path / "proxies" / "clip1.mp4" / "proxy_25.avi"
        assert run.wait.started == clock.now
        wait_for(artifact)
        assert movies[0].proxy.build_25 and movies[0].proxy.build_50 and movies[0].proxy.use_overwrite
        clock.now += 0.5
        assert run.tick() is None  # seen once: the stable clock starts
        clock.now += 1.0
        assert run.tick() is None
        clock.now += 1.5
        assert run.tick() == "done"
        assert run.tick() == "started" and run.current.name == "clip2"
        wait_for(run.artifact)
        clock.now += 0.5
        assert run.tick() is None
        clock.now += 3.0
        assert run.tick() == "done"
    assert run.done and run.built == 2
    assert run.outcomes == [("clip1", "built"), ("clip2", "built")]
    assert run.summary() == "Finished: 2 built, 0 timed out, 0 skipped"


def test_proxy_run_existing_stale_custom_file_and_timeout(bpy, extension, scene, clips: Path, tmp_path: Path):
    from bac_vse_tools.sequential_proxies import ProxyRun, artifact_for

    (movie,) = add_movies(scene, clips, ("clip1",))
    seqed = scene.sequence_editor
    seqed.proxy_storage = "PROJECT"
    seqed.proxy_dir = str(tmp_path / "proxies")
    movie.use_proxy = True
    stale = artifact_for(seqed, movie, 25)
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")
    os.utime(stale, (1_000_000, 1_000_000))

    # Skip Existing (the default) leaves the strip alone.
    run = ProxyRun(scene, [movie], size=25, stable_time=2.0, timeout=60.0, clock=FakeClock())
    with sequencer_override(bpy, scene):
        assert run.tick() == "exists"
    assert run.done and run.skipped == 1 and stale.stat().st_mtime == 1_000_000

    # Without it, Blender rebuilds over the stale file and the wait ignores the old mtime.
    clock = FakeClock()
    run = ProxyRun(scene, [movie], size=25, stable_time=2.0, timeout=60.0, skip_existing=False, clock=clock)
    with sequencer_override(bpy, scene):
        assert run.tick() == "started"
        deadline = time.monotonic() + 60
        while stale.stat().st_mtime == 1_000_000 and time.monotonic() < deadline:
            time.sleep(0.2)
        assert stale.stat().st_mtime != 1_000_000
        clock.now += 0.5
        assert run.tick() is None
        clock.now += 3.0
        assert run.tick() == "done"

    # A strip with a custom proxy file is skipped; a wait that never settles times out.
    movie.proxy.use_proxy_custom_file = True
    run = ProxyRun(scene, [movie], size=25, stable_time=2.0, timeout=5.0, clock=FakeClock())
    with sequencer_override(bpy, scene):
        assert run.tick() == "skipped" and run.done and run.skipped == 1
    movie.proxy.use_proxy_custom_file = False
    clock = FakeClock()
    run = ProxyRun(scene, [movie], size=25, stable_time=2.0, timeout=5.0, skip_existing=False, clock=clock)
    run.trigger = lambda: None  # nothing builds, nothing changes
    with sequencer_override(bpy, scene):
        assert run.tick() == "started"
        clock.now += 4.0
        assert run.tick() is None
        clock.now += 1.5
        assert run.tick() == "timeout" and run.timed_out == 1


def test_proxy_operator_without_strips_is_cancelled(bpy, extension, scene):
    with sequencer_override(bpy, scene):
        assert bpy.ops.sequencer.bac_sequential_proxies() == {"CANCELLED"}


# -- separate meta --------------------------------------------------------------


def make_meta(bpy, scene, clips: Path):
    movies = add_movies(scene, clips, ("clip2", "clip3"))  # 1–101 and 102–252
    for s in strips_of(scene):
        s.select = s in movies
    with sequencer_override(bpy, scene):
        bpy.ops.sequencer.meta_make()
    meta = next(s for s in strips_of(scene) if s.type == "META")
    return meta, movies


def test_separate_meta_preserves_trim(bpy, extension, scene, clips: Path):
    from bac_vse_tools.meta_separate import plan_for, separate_meta

    meta, movies = make_meta(bpy, scene, clips)
    meta.frame_final_start, meta.frame_final_end = 50, 150
    plan = plan_for(meta)
    assert [(p.name, p.action, p.start, p.end) for p in plan] == [
        ("clip2", "clip", 50, 101),
        ("clip3", "clip", 102, 150),
    ]
    with sequencer_override(bpy, scene):
        separate_meta(scene.sequence_editor, meta, plan)
    strips = {s.name: s for s in strips_of(scene)}
    assert "MetaStrip" not in strips
    assert (strips["clip2"].frame_final_start, strips["clip2"].frame_final_end) == (50, 101)
    assert (strips["clip3"].frame_final_start, strips["clip3"].frame_final_end) == (102, 150)


def test_separate_meta_removes_children_outside_and_the_operator_runs(bpy, extension, scene, clips: Path):
    from bac_vse_tools.meta_separate import plan_for

    meta, movies = make_meta(bpy, scene, clips)
    meta.frame_final_start, meta.frame_final_end = 110, 200  # clip2 (1–101) lies entirely before
    plan = plan_for(meta)
    assert [(p.name, p.action) for p in plan] == [("clip2", "remove"), ("clip3", "clip")]
    for s in strips_of(scene):
        s.select = False
    meta.select = True
    with sequencer_override(bpy, scene):
        assert bpy.ops.sequencer.bac_separate_meta_preserve_trim() == {"FINISHED"}
    strips = {s.name: s for s in strips_of(scene)}
    assert set(strips) == {"clip3"}
    assert (strips["clip3"].frame_final_start, strips["clip3"].frame_final_end) == (110, 200)


def test_separate_meta_poll_needs_a_selected_meta(bpy, extension, scene, clips: Path):
    add_movies(scene, clips, ("clip1",))
    assert not bpy.ops.sequencer.bac_separate_meta_preserve_trim.poll()
    meta, _ = make_meta(bpy, scene, clips)
    meta.select = True
    assert bpy.ops.sequencer.bac_separate_meta_preserve_trim.poll()


# -- the extension as Blender installs it ----------------------------------------


def test_zip_installs_and_enables_in_a_fresh_blender(bpy, tmp_path: Path):
    """Build the zip by hand (as the README says) and let a second headless Blender install and enable it."""
    archive = tmp_path / "bac_vse_tools-test.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(EXTENSION_DIR.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                zf.write(path, path.relative_to(EXTENSION_DIR))
    script = tmp_path / "install.py"
    script.write_text(
        f"""
import bpy
bpy.ops.extensions.package_install_files(filepath={str(archive)!r}, repo="user_default", enable_on_install=True)
import bl_ext.user_default.bac_vse_tools as ext
assert hasattr(bpy.types, "SEQUENCER_OT_bac_bulk_import"), "operator missing after install"
assert bpy.context.scene.bac_vse_tools.proxy_size == "25"
assert bpy.context.preferences.addons.get("bl_ext.user_default.bac_vse_tools") is not None
print("INSTALLED", ext.__name__)
""",
        encoding="utf-8",
    )
    env = dict(os.environ, HOME=str(tmp_path / "home"))  # a clean user config, so the install is a first install
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "INSTALLED bl_ext.user_default.bac_vse_tools" in proc.stdout
