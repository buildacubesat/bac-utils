# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Make vse_testkit importable under --import-mode=importlib.
sys.path.insert(0, str(Path(__file__).parent))

from vse_testkit import load_logic, load_package  # noqa: E402


@pytest.fixture(scope="session")
def logic():
    return load_logic()


@pytest.fixture(scope="session")
def bpy():
    return pytest.importorskip("bpy")


@pytest.fixture(scope="session")
def extension(bpy):
    module = load_package()
    module.register()
    yield module
    module.unregister()


@pytest.fixture(scope="session")
def clips(tmp_path_factory) -> Path:
    """Test media made with ffmpeg: three 25 fps clips with audio (2, 4, 6 s), a silent 1 s clip, a 3 s mp3, a 30 fps clip."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is needed to make the test clips")
    folder = tmp_path_factory.mktemp("clips")

    def make(name: str, seconds: float, *, audio: bool = True, video: bool = True, rate: int = 25) -> None:
        args = ["ffmpeg", "-loglevel", "error", "-y"]
        if video:
            args += ["-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=160x120:rate={rate}"]
        if audio:
            args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
        if video:
            args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio:
            args += ["-c:a", "aac" if video else "libmp3lame"]
        args += ["-shortest", str(folder / name)]
        subprocess.run(args, check=True)

    make("clip1.mp4", 2)
    make("clip2.mp4", 4)
    make("clip3.mp4", 6)
    make("silent.mp4", 1, audio=False)
    make("voice.mp3", 3, video=False)
    make("clip30.mp4", 4, rate=30)
    (folder / "notes.txt").write_text("not media", encoding="utf-8")
    (folder / ".hidden.mp4").write_bytes(b"")
    return folder


@pytest.fixture
def scene(bpy, extension):
    """The default scene with an empty sequencer and default settings."""
    scene = bpy.context.scene
    if scene.sequence_editor is not None:
        scene.sequence_editor_clear()
    scene.sequence_editor_create()
    scene.frame_start, scene.frame_current = 1, 1
    scene.render.fps, scene.render.fps_base = 24, 1.0
    settings = scene.bac_vse_tools
    for name in settings.bl_rna.properties.keys():
        if name not in ("rna_type", "name"):
            settings.property_unset(name)
    return scene
