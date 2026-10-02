"""Template values and exporters for the patch antenna types (cross patch, annular ring): the dimensions, stack,
tube, holes and board facts the datasheet templates use. Other antenna types provide their own."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from .drawings import W50, draw_all
from .kicad import make_boards

GROUND_LABEL = {"fr4_1.0": "1.0 mm FR4", "ro4003c_0.813": "0.813 mm RO4003C"}


def patch_report_values(config: Config, design: dict, options: dict | None = None) -> dict:
    """Per-band values: patch dimensions, feed, ordered length and trim."""
    options = options or {}
    order_scale = float(options.get("order_scale", 1.03))
    arm, width = float(design["arm_x_mm"]), float(design["arm_width_mm"])
    order_len = round(arm * order_scale, 1)
    return {"arm": f"{arm:g}", "width": f"{width:g}", "feed": f"{float(design['feed_offset_mm']):g}",
            "pad": f"{float(design['pad_radius_mm']):g}", "order_len": f"{order_len:g}", "trim": f"{(order_len - arm) / 2:.2f}"}


def patch_report_globals(config: Config, options: dict | None = None) -> dict:
    """Shared values: stack, tube, holes, pin, line widths, prototype materials."""
    options = options or {}
    o, s, f = config.outline, config.stack, config.feed
    gb, gap, top = float(s["ground_board_mm"]), float(s["gap_mm"]), float(s["top_board_mm"])
    tube_od = float(o["bore_diameter_mm"]) + 2 * float(o["bore_wall_mm"])
    holes = ", ".join(f"({float(x):g}, {float(y):g})" for x, y in o.get("posts", []))
    gs = options.get("ground_stack", "fr4_1.0")
    return {"gb": f"{gb:g}", "gap": f"{gap:g}", "top": f"{top:g}", "stack": f"{gb + gap + top:.2f}",
            "top_er": f"{float(s['top_board_epsilon_r']):g}", "gb_material": s.get("ground_board_material", "RO4003C"),
            "tube_od": f"{tube_od:g}", "bore": f"{float(o['bore_diameter_mm']):g}", "sleeve": f"{float(o['sleeve_length_mm']):g}",
            "panel": f"{float(o.get('panel_mm', o['arm_length_mm'])):g}", "chamfer": f"{float(o.get('panel_chamfer_mm', 0)):g}", "holes": holes,
            "post_d": f"{float(o.get('post_diameter_mm', 3.0)):g}",
            "pin": f"{float(f['probe_diameter_mm']):g}", "pin_len": f"{gb + gap + top + 1.0:.0f}",
            "clearance": f"{float(f.get('patch_clearance_mm', 2.4)):g}", "land": f"{float(f.get('top_ring_mm', 1.6)):g}",
            "pin_hole": f"{float(f['probe_diameter_mm']) + 0.2:g}",
            "w50_proto": f"{W50[gs]:g}", "w50_flight": f"{W50['ro4003c_0.813']:g}", "ground_proto": GROUND_LABEL[gs],
            "patch_proto_mm": f"{float(options.get('patch_thickness', 0.6)):g}", "order_scale": f"{float(options.get('order_scale', 1.03)):g}"}


def export_drawings(ctx: dict) -> list[str]:
    """Per band: placement drawings and coordinate table."""
    o = ctx["options"]
    return draw_all(ctx["config_path"], ctx["design_path"], Path(ctx["out"]) / "drawings" / ctx["band"], title=ctx["title"],
                    order_scale=float(o.get("order_scale", 1.03)), ground_stack=o.get("ground_stack", "fr4_1.0"))


def export_boards(ctx: dict) -> list[str]:
    """Once: the shared ground board and one patch board per band."""
    o = ctx["options"]
    first = next(iter(ctx["bands"].values()))
    ticks = {bid: tuple((float(x), str(lab)) for x, lab in b.get("extra_ticks", [])) for bid, b in ctx["bands"].items()}
    return make_boards(first["config_path"], {bid: b["design_path"] for bid, b in ctx["bands"].items()}, Path(ctx["out"]) / "boards",
                       ground_stack=o.get("ground_stack", "fr4_1.0"), patch_thickness=float(o.get("patch_thickness", 0.6)),
                       order_scale=float(o.get("order_scale", 1.03)), extra_ticks=ticks)


EXPORTERS = {"drawings": ("band", export_drawings), "boards": ("once", export_boards)}
