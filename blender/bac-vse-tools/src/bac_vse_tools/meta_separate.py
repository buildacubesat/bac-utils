# SPDX-License-Identifier: MIT
"""Separate Meta (Preserve Trim): ungroup meta strips and keep their in and out points on the children.

Blender's own "Separate" restores every child to its full length; a meta
that had been trimmed loses the trim. This operator computes, before
anything changes, what the meta's range means for each child – keep, clip
or remove – and asks before it removes strips that lie entirely outside.
"""

from __future__ import annotations

import bpy
from bpy.types import Operator, Panel

from . import _common
from ._logic import TrimAction, count_actions, trim_plan

__all__ = ["selected_metas", "plan_for", "separate_meta", "BAC_OT_vse_separate_meta", "BAC_PT_vse_strip_utilities"]


def selected_metas(seqed) -> list:
    return [s for s in _common.strips(seqed) if s.type == "META" and s.select]


def plan_for(meta) -> list[TrimAction]:
    bounds = [(c.name, c.frame_final_start, c.frame_final_end) for c in _common.children(meta)]
    return trim_plan(meta.frame_final_start, meta.frame_final_end, bounds)


def separate_meta(seqed, meta, plan: list[TrimAction] | None = None) -> list[TrimAction]:
    """Separate one meta and apply the trim plan to its former children. Returns the plan applied."""
    plan = plan_for(meta) if plan is None else plan
    for strip in _common.all_strips(seqed):
        strip.select = False
    meta.select = True
    seqed.active_strip = meta
    bpy.ops.sequencer.meta_separate()
    everything = _common.all_strips(seqed)
    for item in plan:
        child = everything.get(item.name)
        if child is None:
            continue
        if item.action == "remove":
            _common.remove_strip(seqed, child)
        elif item.action == "clip":
            if child.frame_final_start != item.start:
                child.frame_final_start = item.start
            if child.frame_final_end != item.end:
                child.frame_final_end = item.end
    return plan


class BAC_OT_vse_separate_meta(Operator):
    """Ungroup the selected meta strips and clip their children to the metas' in and out points"""

    bl_idname = "sequencer.bac_separate_meta_preserve_trim"
    bl_label = "Separate Meta (Preserve Trim)"
    bl_options = {"REGISTER", "UNDO"}

    _plans: dict[str, list[TrimAction]] | None = None

    @classmethod
    def poll(cls, context):
        seqed = context.scene.sequence_editor if context.scene else None
        return seqed is not None and any(s.type == "META" and s.select for s in _common.strips(seqed))

    def invoke(self, context, event):
        seqed = context.scene.sequence_editor
        self._plans = {meta.name: plan_for(meta) for meta in selected_metas(seqed)}
        removals = sum(count_actions(plan)["remove"] for plan in self._plans.values())
        if removals:
            noun = "strip lies" if removals == 1 else "strips lie"
            message = f"{removals} {noun} entirely outside the meta's range and will be removed."
            return context.window_manager.invoke_confirm(
                self, event, title="Separate Meta (Preserve Trim)", message=message, confirm_text="Separate"
            )
        return self.execute(context)

    def execute(self, context):
        seqed = context.scene.sequence_editor
        metas = selected_metas(seqed)
        if not metas:
            self.report({"WARNING"}, "No meta strips selected.")
            return {"CANCELLED"}
        plans = self._plans or {}
        totals = {"keep": 0, "clip": 0, "remove": 0}
        for meta in metas:
            applied = separate_meta(seqed, meta, plans.get(meta.name))
            for key, value in count_actions(applied).items():
                totals[key] += value
        self._plans = None
        self.report(
            {"INFO"},
            f"Separated {len(metas)} meta(s): {totals['clip']} strip(s) clipped, {totals['remove']} removed",
        )
        return {"FINISHED"}


class BAC_PT_vse_strip_utilities(Panel):
    bl_label = "Strip Utilities"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = _common.CATEGORY
    bl_order = 2

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="Operations on the selected strips")
        col.operator(BAC_OT_vse_separate_meta.bl_idname, icon="SEQ_STRIP_META")


def strip_menu(self, context):
    self.layout.operator(BAC_OT_vse_separate_meta.bl_idname)
