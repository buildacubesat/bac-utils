# SPDX-License-Identifier: MIT
"""Blender plumbing shared by the three tools: the strips API across versions, status lines, modal timers."""

from __future__ import annotations

__all__ = [
    "CATEGORY",
    "strips",
    "all_strips",
    "children",
    "remove_strip",
    "ensure_sequence_editor",
    "scene_fps",
    "last_end_frame",
    "selection_snapshot",
    "restore_selection",
    "set_status_text",
    "get_status",
    "set_status",
    "draw_status",
    "start_timer",
    "stop_timer",
]

CATEGORY = "VSE Tools"


# -- the strips API, 4.2 through 5.x --------------------------------------------
# Blender 4.4 renamed ``sequences`` to ``strips`` (``sequences_all`` to ``strips_all``,
# ``MetaStrip.sequences`` to ``strips``) and removes the old names in 5.0; 4.2 and 4.3
# have only the old ones.


def strips(seqed):
    """The top-level strip collection of a sequence editor."""
    coll = getattr(seqed, "strips", None)
    return coll if coll is not None else seqed.sequences


def all_strips(seqed):
    """Every strip, including the ones inside metas."""
    coll = getattr(seqed, "strips_all", None)
    return coll if coll is not None else seqed.sequences_all


def children(meta):
    """The strips inside a meta strip."""
    coll = getattr(meta, "strips", None)
    return coll if coll is not None else meta.sequences


def remove_strip(seqed, strip) -> None:
    strips(seqed).remove(strip)


def ensure_sequence_editor(scene):
    if scene.sequence_editor is None:
        scene.sequence_editor_create()
    return scene.sequence_editor


def scene_fps(scene) -> float:
    render = scene.render
    base = render.fps_base if render.fps_base else 1.0
    return float(render.fps) / float(base)


def last_end_frame(scene) -> int:
    """The last frame any top-level strip reaches; ``scene.frame_start - 1`` when the sequencer is empty.

    Top level only: a strip inside a meta may run past the meta's trimmed end
    and would otherwise leave a gap on the timeline.
    """
    seqed = scene.sequence_editor
    last = scene.frame_start - 1
    if seqed:
        for strip in strips(seqed):
            last = max(last, strip.frame_final_end)
    return last


def selection_snapshot(seqed) -> tuple[list, object]:
    """The selected strips and the active one, to put back after a run that selects strips itself."""
    selected = [s for s in all_strips(seqed) if s.select]
    return selected, seqed.active_strip


def restore_selection(seqed, snapshot) -> None:
    selected, active = snapshot
    for strip in all_strips(seqed):
        strip.select = False
    for strip in selected:
        try:
            strip.select = True
        except ReferenceError:  # removed meanwhile
            pass
    try:
        seqed.active_strip = active
    except (ReferenceError, TypeError):
        pass


# -- status ---------------------------------------------------------------------


def set_status_text(context, text: str | None) -> None:
    """The one-line text in Blender's status bar; ``None`` restores the default."""
    workspace = getattr(context, "workspace", None)
    setter = getattr(workspace, "status_text_set", None)
    if callable(setter):
        try:
            setter(text)
        except (RuntimeError, TypeError):
            pass


def get_status(wm, prop: str) -> str:
    return getattr(wm, prop, "") or ""


def set_status(wm, prop: str, text: str) -> None:
    if hasattr(wm, prop):
        setattr(wm, prop, text or "")


def draw_status(layout, wm, prop: str) -> None:
    """The status box a panel shows while an operator runs (empty text draws nothing)."""
    text = get_status(wm, prop)
    if text:
        box = layout.box()
        box.label(text=text)


# -- modal timers ---------------------------------------------------------------


def start_timer(operator, context, interval: float):
    wm = context.window_manager
    operator._timer = wm.event_timer_add(max(0.01, float(interval)), window=context.window)
    wm.modal_handler_add(operator)
    return operator._timer


def stop_timer(operator, context) -> None:
    timer = getattr(operator, "_timer", None)
    if timer is not None:
        try:
            context.window_manager.event_timer_remove(timer)
        except (RuntimeError, ValueError):
            pass
        operator._timer = None
