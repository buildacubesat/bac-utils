# SPDX-License-Identifier: MIT
"""Patch antenna types over a ground plane with a camera bore: the cross patch (lead design) and the annular ring.
Each maps a parameter dict to a Shape (cavity model) and a Model (solver)."""

from __future__ import annotations

import math

from ..config import Config
from ..geometry import (
    PRIORITY_APERTURE,
    PRIORITY_DIELECTRIC,
    PRIORITY_METAL,
    PRIORITY_SLEEVE,
    FieldPlane,
    Model,
    Port,
    Primitive,
    Shape,
    circle,
    cross_outline,
    ring_outline,
    with_hole,
)
from . import AntennaType, Params


def _bore(config: Config) -> tuple[float, float, bool]:
    o = config.outline
    r_in = float(o["bore_diameter_mm"]) / 2
    return r_in, r_in + float(o["bore_wall_mm"]), bool(o["bore_short"])


def chamfered_square(size: float, chamfer: float) -> tuple[tuple[float, float], ...]:
    """Square of `size`, corners cut by `chamfer` along each edge, CCW from (-h, 0)."""
    h, c = size / 2, chamfer
    return (
        (-h, 0.0),
        (-h, -h + c),
        (-h + c, -h),
        (h - c, -h),
        (h, -h + c),
        (h, h - c),
        (h - c, h),
        (-h + c, h),
        (-h, h - c),
    )


def _board_outline(config: Config) -> tuple[tuple[float, float], ...]:
    """Dielectric outline of both boards: the cross, or a chamfered square that fills the mounting area."""
    o = config.outline
    if str(o.get("boards", "cross")) == "square":
        return chamfered_square(float(o["panel_mm"]), float(o.get("panel_chamfer_mm", 0.0)))
    return cross_outline(float(o["arm_length_mm"]), float(o["arm_length_mm"]), float(o["arm_width_mm"]))


def _ground_outline(config: Config) -> tuple[tuple[float, float], ...]:
    """Ground copper: the cross, the board outline (`square`), or a larger conducting face (`panel`)."""
    o = config.outline
    g = str(o.get("ground", "cross"))
    if g == "panel":
        h = float(o["panel_mm"]) / 2
        return ((-h, 0.0), (-h, -h), (h, -h), (h, h), (-h, h))
    if g == "square":
        return chamfered_square(float(o["panel_mm"]), float(o.get("panel_chamfer_mm", 0.0)))
    return cross_outline(float(o["arm_length_mm"]), float(o["arm_length_mm"]), float(o["arm_width_mm"]))


def _feed_points(p: Params, config: Config) -> tuple[tuple[float, float], ...]:
    d = p["feed_offset_mm"]
    if config.feed["mode"] == "dual":
        return ((d, 0.0), (0.0, d))
    return ((d / math.sqrt(2), d / math.sqrt(2)),)


def _stack_primitives(config: Config, patch_points, feeds, pad_r: float) -> tuple[list[Primitive], list[Port]]:
    s, o = config.stack, config.outline
    gb, gap, top = float(s["ground_board_mm"]), float(s["gap_mm"]), float(s["top_board_mm"])
    z_patch = gap + top
    r_in, r_out, shorted = _bore(config)
    sleeve = float(o["sleeve_length_mm"])
    board = _board_outline(config)
    probe_half = float(config.feed["probe_diameter_mm"]) / 2
    port_len = min(0.5, gap / 4)

    prims = [
        Primitive(
            "linpoly",
            "ground_board",
            "dielectric",
            PRIORITY_DIELECTRIC,
            epsilon_r=float(s.get("ground_board_epsilon_r", 4.3)),
            loss_tangent=float(s.get("ground_board_loss_tangent", 0.02)),
            points=board,
            elevation=-gb,
            length=gb,
        ),
        Primitive(
            "linpoly",
            "top_board",
            "dielectric",
            PRIORITY_DIELECTRIC,
            epsilon_r=float(s["top_board_epsilon_r"]),
            loss_tangent=float(s["top_board_loss_tangent"]),
            points=board,
            elevation=gap,
            length=top,
        ),
        Primitive("polygon", "ground", "metal", PRIORITY_METAL, points=_ground_outline(config), elevation=0.0),
        Primitive("polygon", "patch", "metal", PRIORITY_METAL, points=patch_points, elevation=z_patch),
        Primitive(
            "cylinder",
            "camera_tube",
            "metal",
            PRIORITY_SLEEVE,
            start=(0.0, 0.0, -sleeve),
            stop=(0.0, 0.0, z_patch if shorted else 0.0),
            radius=r_out,
        ),
        Primitive(
            "cylinder",
            "optical_bore",
            "air",
            PRIORITY_APERTURE,
            start=(0.0, 0.0, -sleeve - 0.1),
            stop=(0.0, 0.0, z_patch + 0.1),
            radius=r_in,
        ),
    ]
    # standoffs / screws between the boards
    posts = o.get("posts", [])
    if posts:
        pr = float(o.get("post_diameter_mm", 3.0)) / 2
        mat = str(o.get("post_material", "peek"))
        for i, (px, py) in enumerate(posts):
            if mat == "metal":  # screw through both boards, head on the patch side
                prims.append(
                    Primitive(
                        "cylinder",
                        f"post_{i}",
                        "metal",
                        PRIORITY_METAL,
                        start=(px, py, -gb),
                        stop=(px, py, z_patch),
                        radius=pr,
                    )
                )
            else:  # PEEK (er 3.2) or similar, between the copper layers
                prims.append(
                    Primitive(
                        "cylinder",
                        f"post_{i}",
                        "dielectric",
                        PRIORITY_DIELECTRIC + 1,
                        epsilon_r=float(o.get("post_epsilon_r", 3.2)),
                        loss_tangent=float(o.get("post_loss_tangent", 0.003)),
                        start=(px, py, 0.0),
                        stop=(px, py, gap),
                        radius=pr,
                    )
                )
    if float(s["gap_epsilon_r"]) != 1.0:
        prims.insert(
            1,
            Primitive(
                "linpoly",
                "gap_foam",
                "dielectric",
                PRIORITY_DIELECTRIC,
                epsilon_r=float(s["gap_epsilon_r"]),
                loss_tangent=float(s["gap_loss_tangent"]),
                points=board,
                elevation=0.0,
                length=gap,
            ),
        )
    ports = []
    f = config.feed
    through = bool(f.get("through_pin", False))
    for i, (fx, fy) in enumerate(feeds):
        prims.append(
            Primitive(
                "polygon", f"feed_pad_{i}", "metal", PRIORITY_METAL, points=circle(pad_r, 32, fx, fy), elevation=gap
            )
        )
        if through:
            # pin continues through the top board and is soldered on the pad side; the patch copper is cleared
            # around it and a small annular ring (the plated hole's top land) sits inside the clearance.
            clr = float(f.get("patch_clearance_mm", 2.4)) / 2
            ring = float(f.get("top_ring_mm", 1.6)) / 2
            prims.append(
                Primitive(
                    "cylinder",
                    f"pin_clearance_{i}",
                    "dielectric",
                    PRIORITY_METAL + 1,
                    epsilon_r=float(s["top_board_epsilon_r"]),
                    loss_tangent=float(s["top_board_loss_tangent"]),
                    start=(fx, fy, gap + top / 2),
                    stop=(fx, fy, z_patch + 0.05),
                    radius=clr,
                )
            )
            prims.append(
                Primitive(
                    "box",
                    f"probe_{i}",
                    "metal",
                    PRIORITY_METAL + 2,
                    start=(fx - probe_half, fy - probe_half, port_len),
                    stop=(fx + probe_half, fy + probe_half, z_patch),
                )
            )
            if ring > probe_half:
                prims.append(
                    Primitive(
                        "polygon",
                        f"pin_ring_{i}",
                        "metal",
                        PRIORITY_METAL + 2,
                        points=circle(ring, 24, fx, fy),
                        elevation=z_patch,
                    )
                )
        else:
            prims.append(
                Primitive(
                    "box",
                    f"probe_{i}",
                    "metal",
                    PRIORITY_METAL,
                    start=(fx - probe_half, fy - probe_half, port_len),
                    stop=(fx + probe_half, fy + probe_half, gap),
                )
            )
        ports.append(Port((fx, fy, 0.0), (fx, fy, port_len), "z", float(config.feed["impedance_ohm"])))
    return prims, ports


def _mesh_lines(config: Config, xs: list[float], ys: list[float], feeds, pad_r: float) -> dict[str, tuple[float, ...]]:
    s, o = config.stack, config.outline
    r_in, r_out, _ = _bore(config)
    half, w = float(o["arm_length_mm"]) / 2, float(o["arm_width_mm"]) / 2
    common = [-half, half, -w, w, 0.0, -r_in, r_in, -r_out, r_out]
    pr = float(o.get("post_diameter_mm", 3.0)) / 2
    for px, py in o.get("posts", []):
        xs = xs + [px - pr, px, px + pr]
        ys = ys + [py - pr, py, py + pr]
    if str(o.get("ground", "cross")) in ("panel", "square") or str(o.get("boards", "cross")) == "square":
        ph, pc = float(o["panel_mm"]) / 2, float(o.get("panel_chamfer_mm", 0.0))
        common += [-ph, ph, -ph + pc, ph - pc]
    radii = [pad_r]
    if bool(config.feed.get("through_pin", False)):
        radii += [
            float(config.feed["probe_diameter_mm"]) / 2,
            float(config.feed.get("patch_clearance_mm", 2.4)) / 2,
            float(config.feed.get("top_ring_mm", 1.6)) / 2,
        ]
    fx = [c for f in feeds for r in radii for c in (f[0] - r, f[0], f[0] + r)]
    fy = [c for f in feeds for r in radii for c in (f[1] - r, f[1], f[1] + r)]
    gap, top = float(s["gap_mm"]), float(s["top_board_mm"])
    z = (-float(o["sleeve_length_mm"]), -float(s["ground_board_mm"]), 0.0, min(0.5, gap / 4), gap, gap + top)
    return {"x": tuple(common + xs + fx), "y": tuple(common + ys + fy), "z": z}


def _model_extras(config: Config, extent_xy: float) -> dict:
    """The solver-facing facts the backend used to derive from [stack]/[outline] itself."""
    import numpy as np

    s, o, m = config.stack, config.outline, config.mesh
    gap, top, gb = float(s["gap_mm"]), float(s["top_board_mm"]), float(s["ground_board_mm"])
    z_patch = gap + top
    sleeve = float(o["sleeve_length_mm"])
    r_out = float(o["bore_diameter_mm"]) / 2 + float(o["bore_wall_mm"])
    cell = min(float(o["bore_wall_mm"]) / 2, 0.25)
    cell = float(m.get("refine_cell_mm", cell))
    port_len = min(0.5, gap / 4)
    grid_z = np.concatenate(
        [
            np.linspace(port_len, gap, int(m["gap_cells"]) + 1),
            np.linspace(gap, z_patch, int(m["substrate_cells"]) + 1),
            np.arange(-sleeve, -gb, max(2 * cell, sleeve / 10)),
        ]
    )
    half = extent_xy / 2
    above = float(config.raw.get("dump", {}).get("above_patch_mm", 1.0))
    big = 1e9
    return {
        "refine": (r_out + 2.0, cell),
        "grid_lines": {"z": tuple(float(v) for v in grid_z)},
        "bounds": (-half, half, -half, half, -sleeve, z_patch),
        "phase_centre": (0.0, 0.0, z_patch),
        "edge_props": ("patch",),
        "field_planes": (
            FieldPlane("E_gap", (-big, -big, gap / 2), (big, big, gap / 2)),
            FieldPlane("E_top", (-big, -big, z_patch + above), (big, big, z_patch + above)),
            FieldPlane("E_xz", (-big, 0.0, -big), (big, 0.0, big)),
        ),
    }


def _extent_xy(config: Config) -> float:
    o = config.outline
    uses_panel = o.get("ground") in ("panel", "square") or o.get("boards") == "square"
    return max(float(o["arm_length_mm"]), float(o.get("panel_mm", 0)) if uses_panel else 0.0)


def _validate_patch_config(config: Config) -> list[str]:
    problems = []
    for sec in ("stack", "outline", "feed"):
        if sec not in config.geometry:
            problems.append(f"missing [geometry.{sec}] (or legacy [{sec}])")
    if problems:
        return problems
    limit = float(config.stack.get("max_height_mm", 1e9))
    if config.stack_height_mm() > limit + 1e-9:
        problems.append(f"stack is {config.stack_height_mm():.2f} mm, limit {limit} mm")
    if config.feed["mode"] not in {"single", "dual"}:
        problems.append("feed.mode must be single or dual")
    return problems


class CrossPatch(AntennaType):
    """Plus-shaped patch; x and y arms carry the two orthogonal modes. Bore at the centre."""

    name = "cross_patch"
    params = ("arm_x_mm", "arm_y_mm", "arm_width_mm", "feed_offset_mm", "pad_radius_mm")

    def valid(self, p: Params, config: Config) -> bool:
        o, f = config.outline, config.feed
        limit = float(o["arm_length_mm"]) - 2 * float(o["edge_clearance_mm"])
        width_limit = float(o["arm_width_mm"]) - 2 * float(o["edge_clearance_mm"])
        r_in, r_out, shorted = _bore(config)
        hole = r_out if shorted else r_out + float(o["patch_to_bore_clearance_mm"])
        pad_gap = float(f["pad_clearance_mm"])
        if not (p["arm_x_mm"] <= limit and p["arm_y_mm"] <= limit and p["arm_width_mm"] <= width_limit):
            return False
        if p["arm_width_mm"] < 2 * hole + 4:
            return False
        if p["feed_offset_mm"] < float(f["min_offset_mm"]) or p["feed_offset_mm"] - p["pad_radius_mm"] < hole + pad_gap:
            return False
        w = p["arm_width_mm"] / 2
        for fx, fy in _feed_points(p, config):
            # pad fully under copper: inside one arm with margin
            in_x = (
                abs(fy) + p["pad_radius_mm"] + pad_gap <= w
                and abs(fx) + p["pad_radius_mm"] + pad_gap <= p["arm_x_mm"] / 2
            )
            in_y = (
                abs(fx) + p["pad_radius_mm"] + pad_gap <= w
                and abs(fy) + p["pad_radius_mm"] + pad_gap <= p["arm_y_mm"] / 2
            )
            if not (in_x or in_y):
                return False
        return True

    def shape(self, p: Params, config: Config) -> Shape:
        r_in, r_out, shorted = _bore(config)
        hole = 0.0 if shorted else r_out + float(config.outline["patch_to_bore_clearance_mm"])
        return Shape(
            cross_outline(p["arm_x_mm"], p["arm_y_mm"], p["arm_width_mm"]),
            hole,
            r_out if shorted else 0.0,
            _feed_points(p, config),
            p["arm_width_mm"],
        )

    def model(self, p: Params, config: Config) -> Model:
        r_in, r_out, shorted = _bore(config)
        outline = cross_outline(p["arm_x_mm"], p["arm_y_mm"], p["arm_width_mm"])
        # shorted: full cross, the bore cylinder cuts the copper and the tube overlaps it -> joined
        patch = outline if shorted else with_hole(outline, r_out + float(config.outline["patch_to_bore_clearance_mm"]))
        feeds = _feed_points(p, config)
        prims, ports = _stack_primitives(config, patch, feeds, p["pad_radius_mm"])
        ax, ay, w = p["arm_x_mm"] / 2, p["arm_y_mm"] / 2, p["arm_width_mm"] / 2
        lines = _mesh_lines(config, [-ax, ax, -w, w], [-ay, ay, -w, w], feeds, p["pad_radius_mm"])
        notes = ("cross patch; " + ("tube shorts patch to ground" if shorted else "open hole, tube to ground only"),)
        return Model(tuple(prims), tuple(ports), lines, notes=notes, **_model_extras(config, _extent_xy(config)))

    def validate_config(self, config: Config) -> list[str]:
        return _validate_patch_config(config)

    def report_values(self, config: Config, design: dict, options: dict | None = None) -> dict:
        from ..report.patch_values import patch_report_values

        return patch_report_values(config, design, options)

    def report_globals(self, config: Config, options: dict | None = None) -> dict:
        from ..report.patch_values import patch_report_globals

        return patch_report_globals(config, options)

    @property
    def exporters(self) -> dict:
        from ..report.patch_values import EXPORTERS

        return EXPORTERS


class AnnularRing(AntennaType):
    """Ring with a radial CP tab at +x; baseline for comparison."""

    name = "annular_ring"
    params = ("outer_radius_mm", "feed_offset_mm", "perturbation_mm", "pad_radius_mm")
    tab_width_mm = 3.0

    def _hole(self, config: Config) -> float:
        r_in, r_out, shorted = _bore(config)
        return r_out if shorted else r_out + float(config.outline["patch_to_bore_clearance_mm"])

    def valid(self, p: Params, config: Config) -> bool:
        o, f = config.outline, config.feed
        limit = float(o["arm_width_mm"]) / 2 * math.sqrt(2) - float(o["edge_clearance_mm"])
        hole = self._hole(config)
        pad_gap = float(f["pad_clearance_mm"])
        return (
            p["outer_radius_mm"] + p["perturbation_mm"]
            <= min(limit, float(o["arm_length_mm"]) / 2 - float(o["edge_clearance_mm"]))
            and p["outer_radius_mm"] >= hole + 4
            and p["feed_offset_mm"] >= float(f["min_offset_mm"])
            and p["feed_offset_mm"] - p["pad_radius_mm"] >= hole + pad_gap
            and p["feed_offset_mm"] + p["pad_radius_mm"] + pad_gap <= p["outer_radius_mm"]
        )

    def _feeds(self, p: Params, config: Config):
        d = p["feed_offset_mm"]
        if config.feed["mode"] == "dual":
            return ((d, 0.0), (0.0, d))
        return ((d / math.sqrt(2), d / math.sqrt(2)),)

    def shape(self, p: Params, config: Config) -> Shape:
        r_in, r_out, shorted = _bore(config)
        tab = 0.0 if config.feed["mode"] == "dual" else p["perturbation_mm"]
        outline = ring_outline(p["outer_radius_mm"], tab, self.tab_width_mm)
        return Shape(
            outline,
            0.0 if shorted else self._hole(config),
            r_out if shorted else 0.0,
            self._feeds(p, config),
            p["outer_radius_mm"] - self._hole(config),
        )

    def model(self, p: Params, config: Config) -> Model:
        r_in, r_out, shorted = _bore(config)
        tab = 0.0 if config.feed["mode"] == "dual" else p["perturbation_mm"]
        outline = ring_outline(p["outer_radius_mm"], tab, self.tab_width_mm)
        patch = outline if shorted else with_hole(outline, self._hole(config))
        feeds = self._feeds(p, config)
        prims, ports = _stack_primitives(config, patch, feeds, p["pad_radius_mm"])
        ro = p["outer_radius_mm"]
        lines = _mesh_lines(
            config,
            [-ro, ro, ro + tab],
            [-ro, ro, -self.tab_width_mm / 2, self.tab_width_mm / 2],
            feeds,
            p["pad_radius_mm"],
        )
        return Model(
            tuple(prims),
            tuple(ports),
            lines,
            notes=("annular ring baseline",),
            **_model_extras(config, _extent_xy(config)),
        )

    def validate_config(self, config: Config) -> list[str]:
        return _validate_patch_config(config)
