# SPDX-License-Identifier: MIT
"""The extension's settings: one property group on the scene, so they are saved with the file.

The three tools read their options from here; the panels draw them below
the operator buttons, as the Project & Tooling Guide §5.2 asks.
"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup

__all__ = ["BacVseToolsSettings", "SETTINGS_ATTR", "settings_of", "register", "unregister"]

SETTINGS_ATTR = "bac_vse_tools"

PROXY_SCOPES = (
    ("CURRENT", "From Current Frame", "Movie strips that start at or after the current frame"),
    ("SELECTED", "Selected", "The selected movie strips"),
    ("ALL", "All", "Every movie strip in the sequencer"),
)
PROXY_SIZES = (
    ("25", "25 %", "Quarter resolution"),
    ("50", "50 %", "Half resolution"),
    ("75", "75 %", "Three quarters"),
    ("100", "100 %", "Full resolution"),
)


class BacVseToolsSettings(PropertyGroup):
    # Bulk Import
    import_dir: StringProperty(
        name="Folder",
        description="Folder whose video and audio files are imported one after the other, in name order",
        subtype="DIR_PATH",
    )
    pause_seconds: FloatProperty(
        name="Pause (s)",
        description="Wait between two imports so the interface stays responsive",
        default=0.1,
        min=0.01,
        soft_max=1.0,
    )
    retries_per_file: IntProperty(
        name="Retries per File",
        description="How often a file that fails to import is tried again before it is skipped",
        default=2,
        min=0,
        soft_max=5,
    )
    min_length: FloatProperty(
        name="Minimum Length (s)",
        description="Clips shorter than this are left out; 0 keeps every clip",
        default=5.0,
        min=0.0,
        soft_max=30.0,
    )
    match_fps: BoolProperty(
        name="Match Scene FPS",
        description="Set the scene frame rate from the first clip when the sequencer is still empty",
        default=True,
    )
    autosave: BoolProperty(
        name="Autosave Copies",
        description="Write a copy of the file into the autosave folder after every clip; the open file is never saved",
        default=False,
    )
    autosave_dir: StringProperty(
        name="Autosave Folder",
        description="Where the copies go; required when autosave is on",
        subtype="DIR_PATH",
    )

    # Sequential Proxies
    proxy_scope: EnumProperty(
        name="Strips",
        description="Which movie strips get a proxy",
        items=PROXY_SCOPES,
        default="CURRENT",
    )
    proxy_size: EnumProperty(
        name="Proxy Size",
        description="Resolution of the proxies as a share of the original",
        items=PROXY_SIZES,
        default="25",
    )
    skip_existing: BoolProperty(
        name="Skip Existing",
        description="Leave a strip alone when its proxy file already exists instead of building it again",
        default=True,
    )
    stable_time: FloatProperty(
        name="Stable Time (s)",
        description="Seconds the proxy file must stay unchanged before the next strip starts",
        default=2.0,
        min=0.5,
        max=10.0,
    )
    check_interval: FloatProperty(
        name="Check Interval (s)",
        description="Seconds between two looks at the proxy file",
        default=0.5,
        min=0.1,
        max=5.0,
    )
    timeout_seconds: IntProperty(
        name="Timeout (s)",
        description="Seconds to wait for one proxy before the strip is skipped",
        default=180,
        min=10,
        soft_max=1800,
    )


def settings_of(context) -> BacVseToolsSettings:
    return getattr(context.scene, SETTINGS_ATTR)


def register() -> None:
    bpy.utils.register_class(BacVseToolsSettings)
    setattr(bpy.types.Scene, SETTINGS_ATTR, PointerProperty(type=BacVseToolsSettings))


def unregister() -> None:
    if hasattr(bpy.types.Scene, SETTINGS_ATTR):
        delattr(bpy.types.Scene, SETTINGS_ATTR)
    bpy.utils.unregister_class(BacVseToolsSettings)
