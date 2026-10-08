# SPDX-License-Identifier: MIT
"""Helpers for the bac-vse-tools tests: loading the extension from its folder, the way Blender does from the id."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXTENSION_DIR = Path(__file__).resolve().parent.parent / "src" / "bac_vse_tools"
PACKAGE = "bac_vse_tools"
LOGIC_MODULE = "bac_vse_tools_logic"


def load_logic():
    """``_logic`` on its own: it imports nothing from Blender."""
    if LOGIC_MODULE in sys.modules:
        return sys.modules[LOGIC_MODULE]
    spec = importlib.util.spec_from_file_location(LOGIC_MODULE, EXTENSION_DIR / "_logic.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[LOGIC_MODULE] = module  # dataclasses with slots look the module up by name
    spec.loader.exec_module(module)
    return module


def load_package():
    """The whole extension as a package (needs ``bpy``)."""
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    spec = importlib.util.spec_from_file_location(
        PACKAGE, EXTENSION_DIR / "__init__.py", submodule_search_locations=[str(EXTENSION_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


def top_level(seqed):
    coll = getattr(seqed, "strips", None)  # an empty collection is falsy, so no `or` here
    return coll if coll is not None else seqed.sequences


def strips_of(scene):
    seqed = scene.sequence_editor
    coll = getattr(seqed, "strips_all", None)
    return list(coll if coll is not None else seqed.sequences_all)


def add_movies(scene, clips: Path, names=("clip1", "clip2", "clip3")):
    """Movie strips for ``names`` back to back on channel 1, starting at frame 1 (data API, no sound)."""
    seqed = scene.sequence_editor
    coll = top_level(seqed)
    out, start = [], 1
    for name in names:
        strip = coll.new_movie(name, str(clips / f"{name}.mp4"), 1, start)
        out.append(strip)
        start = strip.frame_final_end + 1
    return out


class sequencer_override:
    """A context override with a Video Sequencer area, so the add operators run headless as they do in the editor."""

    def __init__(self, bpy, scene=None):
        self.bpy, self.scene = bpy, scene
        window = bpy.context.window_manager.windows[0]
        area = window.screen.areas[0]
        if area.type != "SEQUENCE_EDITOR":
            area.type = "SEQUENCE_EDITOR"
        region = next(r for r in area.regions if r.type == "WINDOW")
        kwargs = {"window": window, "area": area, "region": region}
        if scene is not None:
            kwargs["scene"] = scene
        self._override = bpy.context.temp_override(**kwargs)

    def __enter__(self):
        return self._override.__enter__()

    def __exit__(self, *exc):
        return self._override.__exit__(*exc)
