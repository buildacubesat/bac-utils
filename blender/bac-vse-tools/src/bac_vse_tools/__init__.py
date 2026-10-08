# SPDX-License-Identifier: MIT
"""Build a CubeSat – bac-vse-tools: the VSE Tools tab of Blender's Video Sequencer.

Three sub-panels under one extension (``blender_manifest.toml`` carries the
metadata; there is no ``bl_info``): Bulk Import, Sequential Proxies and
Strip Utilities. Settings live in a property group on the scene
(``scene.bac_vse_tools``) and are saved with the file; the status lines the
panels show while an operator runs live on the window manager and are not.
"""

from __future__ import annotations

import bpy
from bpy.props import StringProperty

from . import bulk_import, meta_separate, sequential_proxies, settings

__all__ = ["register", "unregister"]

_CLASSES = (
    bulk_import.BAC_OT_vse_bulk_import,
    bulk_import.BAC_PT_vse_bulk_import,
    sequential_proxies.BAC_OT_vse_sequential_proxies,
    sequential_proxies.BAC_PT_vse_sequential_proxies,
    meta_separate.BAC_OT_vse_separate_meta,
    meta_separate.BAC_PT_vse_strip_utilities,
)

_STATUS_PROPS = (
    (bulk_import.STATUS_PROP, "Bulk Import Status"),
    (sequential_proxies.STATUS_PROP, "Sequential Proxies Status"),
)


def register() -> None:
    settings.register()
    for prop, label in _STATUS_PROPS:
        setattr(bpy.types.WindowManager, prop, StringProperty(name=label, default=""))
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.SEQUENCER_MT_strip.append(meta_separate.strip_menu)


def unregister() -> None:
    bpy.types.SEQUENCER_MT_strip.remove(meta_separate.strip_menu)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    for prop, _ in _STATUS_PROPS:
        if hasattr(bpy.types.WindowManager, prop):
            delattr(bpy.types.WindowManager, prop)
    settings.unregister()
