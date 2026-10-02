"""Generate the KiCad board files (ground board, one patch board per band) from the config + designs.

Writes ground_board.kicad_pcb, patch_board_2200.kicad_pcb, patch_board_2400.kicad_pcb (KiCad 8 file format; KiCad 9/10
open and upgrade it). The same geometry as scripts/draw_boards.py: model frame x right, y up, origin at the bore; the
file frame has y down and the board centre at (100, 100) mm. Every footprint is written at rotation 0 with explicit
pad positions, so nothing depends on KiCad's flip convention. Zones are left unfilled – run "Fill all zones" in
pcbnew. The SMP jack is a generic 5-pin right-angle footprint: replace it with the manufacturer's before ordering.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import tomllib
import uuid

ORIGIN = (100.0, 100.0)
HYB = {"len": 14.22, "wid": 5.08, "pad": 1.5, "dx": 6.335, "dy": 1.765}   # X3C22E3-03S, datasheet p. 1
W50 = {"fr4_1.0": 1.94, "ro4003c_0.813": 1.82}


_UID_NS = uuid.UUID("6f2a1c0e-3b7d-4a55-9c1e-bac0a17e7a11")   # bac-antenna-optimizer board writer
_uid_scope = ["board"]
_uid_count = [0]


def uid_scope(name: str) -> None:
    """Start a new deterministic UUID sequence, one per board file, so regenerating an unchanged design
    reproduces the file byte for byte (a regenerate that changes nothing must leave git clean)."""
    _uid_scope[0] = name
    _uid_count[0] = 0


def uid():
    _uid_count[0] += 1
    return str(uuid.uuid5(_UID_NS, f"{_uid_scope[0]}:{_uid_count[0]}"))


def F(p):
    """model (x, y) -> file (x, y): y down, offset to the page."""
    return (ORIGIN[0] + p[0], ORIGIN[1] - p[1])


def xy(p):
    q = F(p)
    return f"(xy {q[0]:.4f} {q[1]:.4f})"


def chamfered(size, ch):
    h = size / 2
    return [(h - ch, h), (-h + ch, h), (-h, h - ch), (-h, -h + ch), (-h + ch, -h), (h - ch, -h), (h, -h + ch), (h, h - ch)]


def cross(L, w):
    h, q = L / 2, w / 2
    return [(-h, -q), (-q, -q), (-q, -h), (q, -h), (q, -q), (h, -q), (h, q), (q, q), (q, h), (-q, h), (-q, q), (-h, q)]


def circle_pts(c, r, n=48):
    return [(c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def add(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1])


class Board:
    def __init__(self, thickness: float, nets: list[str]):
        self.thickness = thickness
        self.nets = nets                      # index = net number; nets[0] == ""
        self.items: list[str] = []

    def net(self, name):
        return self.nets.index(name)

    # --- graphics --------------------------------------------------------------------------------
    def outline(self, pts):
        for a, b in zip(pts, pts[1:] + pts[:1]):
            fa, fb = F(a), F(b)
            self.items.append(f'(gr_line (start {fa[0]:.4f} {fa[1]:.4f}) (end {fb[0]:.4f} {fb[1]:.4f}) '
                              f'(stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{uid()}"))')

    def line(self, a, b, layer, width=0.15):
        fa, fb = F(a), F(b)
        self.items.append(f'(gr_line (start {fa[0]:.4f} {fa[1]:.4f}) (end {fb[0]:.4f} {fb[1]:.4f}) '
                          f'(stroke (width {width}) (type default)) (layer "{layer}") (uuid "{uid()}"))')

    def circle(self, c, r, layer, width=0.12, fill=False):
        fc = F(c)
        self.items.append(f'(gr_circle (center {fc[0]:.4f} {fc[1]:.4f}) (end {fc[0] + r:.4f} {fc[1]:.4f}) '
                          f'(stroke (width {width}) (type default)) (fill {"solid" if fill else "none"}) (layer "{layer}") (uuid "{uid()}"))')

    def poly(self, pts, layer, fill=True, width=0.0):
        self.items.append(f'(gr_poly (pts {" ".join(xy(p) for p in pts)}) (stroke (width {width}) (type default)) '
                          f'(fill {"solid" if fill else "none"}) (layer "{layer}") (uuid "{uid()}"))')

    def text(self, s, p, layer, size=1.0, mirror=False, justify="left"):
        fp = F(p)
        j = f"(justify {justify}{' mirror' if mirror else ''})"
        self.items.append(f'(gr_text "{s}" (at {fp[0]:.4f} {fp[1]:.4f} 0) (layer "{layer}") (uuid "{uid()}") '
                          f'(effects (font (size {size} {size}) (thickness {size * 0.15:.3f})) {j}))')

    # --- copper ----------------------------------------------------------------------------------
    def track(self, pts, width, net, layer="B.Cu"):
        for a, b in zip(pts, pts[1:]):
            fa, fb = F(a), F(b)
            self.items.append(f'(segment (start {fa[0]:.4f} {fa[1]:.4f}) (end {fb[0]:.4f} {fb[1]:.4f}) (width {width}) '
                              f'(layer "{layer}") (net {self.net(net)}) (uuid "{uid()}"))')

    def via(self, p, net, size=1.0, drill=0.5):
        fp = F(p)
        self.items.append(f'(via (at {fp[0]:.4f} {fp[1]:.4f}) (size {size}) (drill {drill}) (layers "F.Cu" "B.Cu") '
                          f'(net {self.net(net)}) (uuid "{uid()}"))')

    def zone(self, pts, net, layer, name, clearance=0.3, min_thickness=0.25):
        self.items.append(f'(zone (net {self.net(net)}) (net_name "{net}") (layer "{layer}") (uuid "{uid()}") (name "{name}") '
                          f'(hatch edge 0.5) (connect_pads yes (clearance {clearance})) (min_thickness {min_thickness}) '
                          f'(filled_areas_thickness no) (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5)) '
                          f'(polygon (pts {" ".join(xy(p) for p in pts)})))')

    def keepout(self, pts, layer, name):
        self.items.append(f'(zone (net 0) (net_name "") (layers "{layer}") (uuid "{uid()}") (name "{name}") (hatch edge 0.5) '
                          f'(connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no) '
                          f'(keepout (tracks allowed) (vias allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) '
                          f'(fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts {" ".join(xy(p) for p in pts)})))')

    # --- footprints ------------------------------------------------------------------------------
    def footprint(self, lib, ref, value, at, layer, pads, lines=(), attr="smd", ref_offset=(0.0, 3.0), text_layer=None):
        """pads: list of dicts with keys kind (smd|thru_hole|np_thru_hole), shape, at (model offset), size, drill, layers, net, number.
        lines: (a, b, layer) in model offsets. All offsets are in the model frame relative to `at`."""
        fa = F(at)
        back = layer == "B.Cu"
        tl = text_layer or ("B.SilkS" if back else "F.SilkS")
        fl = "B.Fab" if back else "F.Fab"
        mir = " mirror" if back else ""
        body = [f'(footprint "{lib}" (layer "{layer}") (uuid "{uid()}") (at {fa[0]:.4f} {fa[1]:.4f})',
                f'  (property "Reference" "{ref}" (at {ref_offset[0]:.3f} {-ref_offset[1]:.3f} 0) (layer "{tl}") (uuid "{uid()}") '
                f'(effects (font (size 1 1) (thickness 0.15)) (justify{mir})))',
                f'  (property "Value" "{value}" (at {ref_offset[0]:.3f} {-ref_offset[1] + 1.5:.3f} 0) (layer "{fl}") (uuid "{uid()}") '
                f'(effects (font (size 1 1) (thickness 0.15)) (justify{mir})))',
                f'  (attr {attr})']
        for a, b, lay in lines:
            body.append(f'  (fp_line (start {a[0]:.4f} {-a[1]:.4f}) (end {b[0]:.4f} {-b[1]:.4f}) (stroke (width 0.1) (type default)) '
                        f'(layer "{lay}") (uuid "{uid()}"))')
        for p in pads:
            kind, shape = p["kind"], p.get("shape", "circle")
            ox, oy = p["at"]
            size = p["size"]
            sz = f"(size {size[0]} {size[1]})" if isinstance(size, tuple) else f"(size {size} {size})"
            drill = f' (drill {p["drill"]})' if "drill" in p else ""
            layers = " ".join(f'"{l}"' for l in p["layers"])
            net = f' (net {self.net(p["net"])} "{p["net"]}")' if p.get("net") else ""
            num = p.get("number", "")
            extra = f' (clearance {p["clearance"]})' if "clearance" in p else ""
            body.append(f'  (pad "{num}" {kind} {shape} (at {ox:.4f} {-oy:.4f}) {sz}{drill} (layers {layers}){net}{extra} (uuid "{uid()}"))')
        body.append(")")
        self.items.append("\n".join(body))

    # --- file ------------------------------------------------------------------------------------
    def write(self, path: Path, title: str):
        layers = ['(0 "F.Cu" signal)', '(31 "B.Cu" signal)', '(32 "B.Adhes" user "B.Adhesive")', '(33 "F.Adhes" user "F.Adhesive")',
                  '(34 "B.Paste" user)', '(35 "F.Paste" user)', '(36 "B.SilkS" user "B.Silkscreen")', '(37 "F.SilkS" user "F.Silkscreen")',
                  '(38 "B.Mask" user)', '(39 "F.Mask" user)', '(40 "Dwgs.User" user "User.Drawings")', '(41 "Cmts.User" user "User.Comments")',
                  '(42 "Eco1.User" user "User.Eco1")', '(43 "Eco2.User" user "User.Eco2")', '(44 "Edge.Cuts" user)', '(45 "Margin" user)',
                  '(46 "B.CrtYd" user "B.Courtyard")', '(47 "F.CrtYd" user "F.Courtyard")', '(48 "B.Fab" user)', '(49 "F.Fab" user)']
        nets = "\n".join(f'  (net {i} "{n}")' for i, n in enumerate(self.nets))
        head = (f'(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")\n'
                f'  (general (thickness {self.thickness}) (legacy_teardrops no))\n  (paper "A4")\n'
                f'  (title_block (title "{title}") (date "2026-09-23") (rev "v2") (company "Build a CubeSat"))\n'
                f'  (layers\n    ' + "\n    ".join(layers) + '\n  )\n'
                f'  (setup (pad_to_mask_clearance 0.05) (allow_soldermask_bridges_in_footprints no))\n' + nets + "\n")
        body = "\n".join("  " + it.replace("\n", "\n  ") for it in self.items)
        path.write_text(head + body + "\n)\n")


# ================================================================================================
def ground_board(cfg: dict, design: dict, stack: str) -> Board:
    g = cfg.get("geometry", cfg)          # 0.6 layout or legacy top-level sections
    o, f, s = g["outline"], g["feed"], g["stack"]
    W = W50[stack]
    thickness = 1.0 if stack == "fr4_1.0" else 0.813
    panel, ch = float(o["panel_mm"]), float(o.get("panel_chamfer_mm", 0.0))
    posts = [(float(x), float(y)) for x, y in o["posts"]]
    tube_od = float(o["bore_diameter_mm"]) + 2 * float(o["bore_wall_mm"])
    feed = float(design["feed_offset_mm"])
    pin_hole = round(float(f["probe_diameter_mm"]) + 0.2, 2)

    b = Board(thickness, ["", "GND", "HYB1", "RF_IN", "HYB2", "HYB3", "HYB4"])
    b.outline(chamfered(panel, ch))
    b.text("BAC S-band cross patch – ground board – v2 2026-09-23 – top side: ground plane", (-38, 41.5), "F.SilkS", 1.2)

    # hybrid at (20, 20), long axis on the 135 deg line, pins 1 & 4 toward -45 deg
    C = (20.0, 20.0)
    u = (math.cos(math.radians(-45)), math.sin(math.radians(-45)))
    v = (math.cos(math.radians(45)), math.sin(math.radians(45)))

    def P(a, c):                      # part (X, Y) -> model
        return (C[0] + a * u[0] + c * v[0], C[1] + a * u[1] + c * v[1])

    def rel(p):                       # model -> offset from C
        return (p[0] - C[0], p[1] - C[1])

    pins = {1: P(HYB["dx"], HYB["dy"]), 2: P(-HYB["dx"], HYB["dy"]), 3: P(-HYB["dx"], -HYB["dy"]), 4: P(HYB["dx"], -HYB["dy"])}
    body = [P(sx * HYB["len"] / 2, sy * HYB["wid"] / 2) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    hyb_lines = [(rel(a), rel(c), "B.Fab") for a, c in zip(body, body[1:] + body[:1])]
    court = [P(sx * (HYB["len"] / 2 + 0.5), sy * (HYB["wid"] / 2 + 0.5)) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    hyb_lines += [(rel(a), rel(c), "B.CrtYd") for a, c in zip(court, court[1:] + court[:1])]
    m = P(5.2, 1.4)
    hyb_lines += [(rel(add(m, (-0.3, 0))), rel(add(m, (0.3, 0))), "B.SilkS"), (rel(add(m, (0, -0.3))), rel(add(m, (0, 0.3))), "B.SilkS")]
    b.footprint("BAC:X3C22E3-03S", "U1", "X3C22E3-03S", C, "B.Cu",
                [{"kind": "smd", "shape": "rect", "at": rel(pins[n]), "size": HYB["pad"], "layers": ["B.Cu", "B.Paste", "B.Mask"],
                  "net": f"HYB{n}", "number": str(n)} for n in (1, 2, 3, 4)], hyb_lines, ref_offset=(0.0, -5.0))

    # probe pins: plated hole, pad on the underside only, copper-free circle in the ground plane
    for ref, p, net in (("P1", (feed, 0.0), "HYB4"), ("P2", (0.0, feed), "HYB3")):
        b.footprint("BAC:ProbePin_1.0mm", ref, "pin 1.0 x 7", p, "B.Cu",
                    [{"kind": "thru_hole", "at": (0, 0), "size": 2.4, "drill": pin_hole, "layers": ["B.Cu", "B.Mask"], "net": net, "number": "1"}],
                    attr="through_hole", ref_offset=(0.0, -2.6))
        b.keepout(circle_pts(p, 1.3), "F.Cu", f"{ref} ground clearance")

    # mounting holes, plated, chassis ground
    for i, p in enumerate(posts, start=1):
        b.footprint("MountingHole:M3_Pad", f"H{i}", "M3", p, "F.Cu",
                    [{"kind": "thru_hole", "at": (0, 0), "size": 6.0, "drill": 3.2, "layers": ["*.Cu", "*.Mask"], "net": "GND", "number": "1"}],
                    attr="through_hole", ref_offset=(0.0, 4.2))

    # bore: NPTH, mask opened to 15 mm for the tube fillet on the ground-plane side
    b.footprint("BAC:CameraBore", "T1", f"tube OD {tube_od:g}", (0.0, 0.0), "F.Cu",
                [{"kind": "np_thru_hole", "at": (0, 0), "size": 15.0, "drill": round(tube_od + 0.2, 2), "layers": ["F.Mask", "B.Mask"]}],
                attr="through_hole", ref_offset=(0.0, -9.0))
    b.circle((0, 0), tube_od / 2, "F.Fab")

    # SMP jack: generic 5-pin right-angle THT placeholder, signal pin at (30, -13), axis -45 deg
    S = (30.0, -13.0)
    d = (math.cos(math.radians(-45)), math.sin(math.radians(-45)))
    n_ = (-d[1], d[0])
    legs = [add(add(S, d, k), n_, sgn * 2.5) for k in (1.5, 4.5) for sgn in (1, -1)]
    smp_pads = [{"kind": "thru_hole", "at": (0, 0), "size": 1.6, "drill": 0.9, "layers": ["B.Cu", "B.Mask"], "net": "RF_IN", "number": "1"}]
    smp_pads += [{"kind": "thru_hole", "at": (g[0] - S[0], g[1] - S[1]), "size": 1.8, "drill": 1.1, "layers": ["*.Cu", "*.Mask"], "net": "GND",
                  "number": str(i + 2)} for i, g in enumerate(legs)]
    sc = add(S, d, 3.0)
    box = [add(add(sc, d, sx * 3.0), n_, sy * 3.0) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    smp_lines = [((a[0] - S[0], a[1] - S[1]), (c[0] - S[0], c[1] - S[1]), "B.Fab") for a, c in zip(box, box[1:] + box[:1])]
    face = add(S, d, 6.0)
    smp_lines.append(((face[0] - S[0], face[1] - S[1]), (face[0] - S[0] + 3 * d[0], face[1] - S[1] + 3 * d[1]), "B.SilkS"))
    b.footprint("BAC:SMP_RightAngle_THT_placeholder", "J1", "SMP jack RA THT (replace with vendor footprint)", S, "B.Cu", smp_pads, smp_lines,
                attr="through_hole", ref_offset=(0.0, 3.0))
    b.keepout(circle_pts(S, 1.3), "F.Cu", "J1 signal clearance")

    # nodes and traces
    ex = HYB["dx"] + 3.5            # 3.5 mm exit segments: room for the 0603 link between the hybrid pad and the node
    N1, N2, X4, X3 = P(ex, HYB["dy"]), P(-ex, HYB["dy"]), P(ex, -HYB["dy"]), P(-ex, -HYB["dy"])
    PX, PY = (feed, 0.0), (0.0, feed)

    def mitre(corner, d_in, d_out, k=1.0):
        return [add(corner, d_in, -k), add(corner, d_out, k)]

    dm = (-0.7071, -0.7071)
    dir_x4 = ((PX[0] - X4[0]), (PX[1] - X4[1])); l = math.hypot(*dir_x4); dir_x4 = (dir_x4[0] / l, dir_x4[1] / l)
    dir_x3 = ((PY[0] - X3[0]), (PY[1] - X3[1])); l = math.hypot(*dir_x3); dir_x3 = (dir_x3[0] / l, dir_x3[1] / l)
    b.track([pins[4], *mitre(X4, u, dir_x4), PX], W, "HYB4")
    b.track([pins[3], *mitre(X3, (-u[0], -u[1]), dir_x3), PY], W, "HYB3")
    # pin 1 -> R1 (R_in1) -> N1 -> SMP
    r1 = ((pins[1][0] + N1[0]) / 2, (pins[1][1] + N1[1]) / 2)
    b.footprint("Resistor_SMD:R_0603", "R1", "0R (R_in1, populated for RHCP)", r1, "B.Cu",
                [{"kind": "smd", "shape": "rect", "at": (-0.8 * u[0], -0.8 * u[1]), "size": 0.9, "layers": ["B.Cu", "B.Paste", "B.Mask"], "net": "HYB1", "number": "1"},
                 {"kind": "smd", "shape": "rect", "at": (0.8 * u[0], 0.8 * u[1]), "size": 0.9, "layers": ["B.Cu", "B.Paste", "B.Mask"], "net": "RF_IN", "number": "2"}],
                ref_offset=(0.0, -1.8))
    b.track([pins[1], add(r1, u, -0.8)], W, "HYB1")
    b.track([add(r1, u, 0.8), N1, S], W, "RF_IN")
    # swap: N1 -> R2 (R_in2, DNP) -> around the outer side -> N2
    sw1, sw2 = P(ex, 4.3), P(-ex, 4.3)
    r2 = ((N1[0] + sw1[0]) / 2, (N1[1] + sw1[1]) / 2)
    b.footprint("Resistor_SMD:R_0603", "R2", "0R (R_in2, DNP – populate for LHCP)", r2, "B.Cu",
                [{"kind": "smd", "shape": "rect", "at": (-0.8 * v[0], -0.8 * v[1]), "size": 0.9, "layers": ["B.Cu", "B.Paste", "B.Mask"], "net": "RF_IN", "number": "1"},
                 {"kind": "smd", "shape": "rect", "at": (0.8 * v[0], 0.8 * v[1]), "size": 0.9, "layers": ["B.Cu", "B.Paste", "B.Mask"], "net": "HYB2", "number": "2"}],
                ref_offset=(2.2, 0.0))
    b.track([N1, add(r2, v, -0.8)], W, "RF_IN")
    b.track([add(r2, v, 0.8), *mitre(sw1, v, (-u[0], -u[1])), *mitre(sw2, (-u[0], -u[1]), (-v[0], -v[1])), N2, pins[2]], W, "HYB2")
    # loads: R3 = R_L2 at pin 2 (populated), R4 = R_L1 at pin 1 (DNP); two ground vias each
    for ref, node, sgn, value, net_a in (("R3", N2, -1, "50R 1W 1206 (R_L2, populated for RHCP)", "HYB2"),
                                        ("R4", N1, 1, "50R 1W 1206 (R_L1, DNP – populate for LHCP)", "RF_IN")):
        centre = add(node, u, sgn * 2.5)
        pa, pb_ = add(centre, u, -sgn * 1.475), add(centre, u, sgn * 1.475)
        b.footprint("Resistor_SMD:R_1206", ref, value, centre, "B.Cu",
                    [{"kind": "smd", "shape": "rect", "at": (pa[0] - centre[0], pa[1] - centre[1]), "size": 1.6, "layers": ["B.Cu", "B.Paste", "B.Mask"], "net": net_a, "number": "1"},
                     {"kind": "smd", "shape": "rect", "at": (pb_[0] - centre[0], pb_[1] - centre[1]), "size": 1.6, "layers": ["B.Cu", "B.Paste", "B.Mask"], "net": "GND", "number": "2"}],
                    ref_offset=(0.0, -2.2))
        b.track([node, pa], W, net_a)
        for off in (-0.9, 0.9):
            via_p = add(add(centre, u, sgn * 3.6), v, off)
            b.track([pb_, via_p], 0.6, "GND")
            b.via(via_p, "GND")

    # ground plane on the top side
    b.zone(chamfered(panel - 0.6, max(ch - 0.3, 0)), "GND", "F.Cu", "GND plane", clearance=0.3)
    # labels (underside, mirrored)
    for s_, p in (("pin4 -> x", (16.5, 6.5)), ("pin3 -> y", (2.5, 19.0)), ("RF in", (31.5, -1.0)), ("swap (DNP)", (26.5, 26.5)),
                  ("R_in1", (23.5, 11.2)), ("R_in2", (30.5, 15.5)), ("R_L2", (7.5, 30.5)), ("R_L1 DNP", (33.5, 8.5))):
        b.text(s_, p, "B.SilkS", 0.9, mirror=True)
    b.text("BAC S-band cross patch – ground board – underside", (38, -41.5), "B.SilkS", 1.2, mirror=True, justify="right")
    return b


def patch_board(cfg: dict, design: dict, order_scale: float, thickness: float, band_label: str, extra_ticks=()) -> Board:
    g = cfg.get("geometry", cfg)
    o, f = g["outline"], g["feed"]
    panel, ch = float(o["panel_mm"]), float(o.get("panel_chamfer_mm", 0.0))
    posts = [(float(x), float(y)) for x, y in o["posts"]]
    tube_od = float(o["bore_diameter_mm"]) + 2 * float(o["bore_wall_mm"])
    feed, pad_r = float(design["feed_offset_mm"]), float(design["pad_radius_mm"])
    arm, width = float(design["arm_x_mm"]), float(design["arm_width_mm"])
    L_order = round(arm * order_scale, 1)
    pin_hole = round(float(f["probe_diameter_mm"]) + 0.2, 2)
    clear, ring = float(f.get("patch_clearance_mm", 2.4)), float(f.get("top_ring_mm", 1.6))

    b = Board(thickness, ["", "PATCH", "FEEDX", "FEEDY"])
    b.outline(chamfered(panel, ch))
    b.zone(cross(L_order, width), "PATCH", "F.Cu", "patch", clearance=0.0)
    # no solder mask on either side: full-board openings
    for layer in ("F.Mask", "B.Mask"):
        b.poly(chamfered(panel + 1.0, ch), layer)
    # feeds: pad on the underside, plated hole with a small top land, copper-free circle in the patch
    for ref, p, net in (("F1", (feed, 0.0), "FEEDX"), ("F2", (0.0, feed), "FEEDY")):
        b.footprint("BAC:FeedPad", ref, f"pad r {pad_r:g}", p, "B.Cu",
                    [{"kind": "smd", "shape": "circle", "at": (0, 0), "size": round(2 * pad_r, 2), "layers": ["B.Cu", "B.Mask"], "net": net, "number": "1"},
                     {"kind": "thru_hole", "at": (0, 0), "size": ring, "drill": pin_hole, "layers": ["*.Cu", "*.Mask"], "net": net, "number": "1"}],
                    attr="through_hole", ref_offset=(0.0, -3.4))
        b.keepout(circle_pts(p, clear / 2), "F.Cu", f"{ref} patch clearance")
    for i, p in enumerate(posts, start=1):
        b.footprint("MountingHole:M3", f"H{i}", "M3", p, "F.Cu",
                    [{"kind": "np_thru_hole", "at": (0, 0), "size": 3.2, "drill": 3.2, "layers": ["F.Mask", "B.Mask"]}],
                    attr="through_hole", ref_offset=(0.0, 4.2))
    b.footprint("BAC:CameraBore", "T1", f"tube OD {tube_od:g}", (0.0, 0.0), "F.Cu",
                [{"kind": "np_thru_hole", "at": (0, 0), "size": round(tube_od + 0.2, 2), "drill": round(tube_od + 0.2, 2), "layers": ["F.Mask", "B.Mask"]}],
                attr="through_hole", ref_offset=(0.0, -9.0))
    # trim ticks on the silkscreen at the design length (and any extra lengths)
    for i, (L, lab) in enumerate(((arm, f"{arm:g}"), *extra_ticks)):
        h = L / 2
        for sx in (1, -1):
            for sy in (1, -1):
                b.line((sx * h, sy * (width / 2 + 0.6)), (sx * h, sy * (width / 2 + 2.6)), "F.SilkS", 0.2)
                b.line((sy * (width / 2 + 0.6), sx * h), (sy * (width / 2 + 2.6), sx * h), "F.SilkS", 0.2)
        b.text(lab, (h + 0.4, width / 2 + 2.9 + 1.6 * i), "F.SilkS", 0.9)
    b.text(f"BAC S-band cross patch – patch board {band_label} – ordered {L_order:g} x {width:g}, trim to {arm:g}", (-38, 41.5), "F.SilkS", 1.2)
    b.text("no solder mask, ENIG", (-38, -42.5), "F.SilkS", 1.0)
    return b


def make_boards(config: Path, designs: dict[str, Path], out: Path, ground_stack: str = "fr4_1.0", patch_thickness: float = 0.6,
                order_scale: float = 1.03, extra_ticks: dict[str, tuple] | None = None) -> list[str]:
    """designs: {band_id: design JSON path}; the first band's config drives the shared ground board."""
    cfg = tomllib.loads(Path(config).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    bands = list(designs)
    first = json.loads(Path(designs[bands[0]]).read_text())
    uid_scope("ground_board")
    ground_board(cfg, first, ground_stack).write(out / "ground_board.kicad_pcb", "BAC S-band cross patch – ground board")
    written = ["ground_board.kicad_pcb"]
    for band, path in designs.items():
        des = json.loads(Path(path).read_text())
        ticks = (extra_ticks or {}).get(band, ())
        uid_scope(f"patch_board_{band}")
        patch_board(cfg, des, order_scale, patch_thickness, band, extra_ticks=ticks).write(
            out / f"patch_board_{band}.kicad_pcb", f"BAC S-band cross patch – patch board {band}")
        written.append(f"patch_board_{band}.kicad_pcb")
    return written
