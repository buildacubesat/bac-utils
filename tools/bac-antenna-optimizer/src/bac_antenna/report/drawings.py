"""Placement drawings for the two boards from a config + design (ground board, patch board, stack section).

Writes <out>_ground.svg, <out>_top.svg, <out>_stack.svg and <out>_coordinates.md (SVG only; a raster copy of a
drawing was never used by the templates and cairo does not render text reproducibly).
Frame: x right, y up, origin at the bore centre, seen from the antenna side; KiCad uses (x, -y). Ground-board
components sit on the underside and are drawn through the board. The hybrid stays at (20, 20) on the 45 deg
diagonal for every variant; only the two probe vias move with the feed offset.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import tomllib

W50 = {"fr4_1.0": 1.94, "ro4003c_0.813": 1.82}
HYB = {"len": 14.22, "wid": 5.08, "pin": 1.24, "pin_dx": 6.335, "pin_dy": 1.765}   # X3C22E3-03S, datasheet p. 1
FONT = 'font-family="Helvetica, Arial, sans-serif"'


def attrs(**kw):
    return " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in kw.items())


def circ(c, r, **kw):
    return f'<circle cx="{c[0]:.3f}" cy="{c[1]:.3f}" r="{r:.3f}" {attrs(**kw)}/>'


def poly(pts, close=False, **kw):
    d = " ".join(f"{x:.3f},{y:.3f}" for x, y in pts)
    return f'<polygon points="{d}" {attrs(**kw)}/>' if close else f'<polyline points="{d}" fill="none" {attrs(**kw)}/>'


def rect(cx, cy, w, h, ang, **kw):
    return (f'<rect x="{cx - w / 2:.3f}" y="{cy - h / 2:.3f}" width="{w:.3f}" height="{h:.3f}" '
            f'transform="rotate({ang:.2f} {cx:.3f} {cy:.3f})" {attrs(**kw)}/>')


def text(p, s, size=1.3, anchor="middle", **kw):
    s = s.replace("&", "&amp;").replace("<", "&lt;")
    return f'<text x="{p[0]:.3f}" y="{-p[1]:.3f}" font-size="{size}" text-anchor="{anchor}" {FONT} {attrs(**kw)}>{s}</text>'


def svg_doc(geometry, labels, notes):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-58 -50 116 112" width="1160" height="1120">',
           '<rect x="-58" y="-50" width="116" height="112" fill="#fff"/>', '<g transform="scale(1,-1)">', *geometry, '</g>', *labels]
    for i, n in enumerate(notes):
        n = n.replace("&", "&amp;").replace("<", "&lt;")
        out.append(f'<text x="-56.5" y="{51.5 + 1.9 * i:.1f}" font-size="{1.5 if i == 0 else 1.25}" '
                   f'font-weight="{"bold" if i == 0 else "normal"}" {FONT}>{n}</text>')
    out.append("</svg>")
    return "\n".join(out)


def chamfered(size, ch):
    h = size / 2
    return [(h - ch, h), (-h + ch, h), (-h, h - ch), (-h, -h + ch), (-h + ch, -h), (h - ch, -h), (h, -h + ch), (h, h - ch)]


def cross(L, w):
    h, q = L / 2, w / 2
    return [(-h, -q), (-q, -q), (-q, -h), (q, -h), (q, -q), (h, -q), (h, q), (q, q), (q, h), (-q, h), (-q, q), (-h, q)]


class Geometry:
    def __init__(self, cfg: dict, design: dict, w50: float):
        g = cfg.get("geometry", cfg)          # 0.6 layout or legacy top-level sections
        o, f, s = g["outline"], g["feed"], g["stack"]
        self.panel, self.chamfer = float(o["panel_mm"]), float(o.get("panel_chamfer_mm", 0.0))
        self.posts = [(float(x), float(y)) for x, y in o.get("posts", [])]
        self.post_hole = float(o.get("post_diameter_mm", 3.0)) + 0.2
        self.bore_in = float(o["bore_diameter_mm"])
        self.tube_od = self.bore_in + 2 * float(o["bore_wall_mm"])
        self.sleeve = float(o["sleeve_length_mm"])
        self.feed = float(design["feed_offset_mm"])
        self.pad_r = float(design["pad_radius_mm"])
        self.arm = float(design["arm_x_mm"])
        self.width = float(design["arm_width_mm"])
        self.pin = float(f["probe_diameter_mm"])
        self.pin_hole = round(self.pin + 0.2, 2)
        self.clear = float(f.get("patch_clearance_mm", 2.4))
        self.ring = float(f.get("top_ring_mm", 1.6))
        self.through = bool(f.get("through_pin", False))
        self.gap, self.gb, self.top = float(s["gap_mm"]), float(s["ground_board_mm"]), float(s["top_board_mm"])
        self.w50 = w50


def ground_board(gm: Geometry, title: str, w50_label: str):
    W = gm.w50
    C = (20.0, 20.0)
    u = (math.cos(math.radians(-45)), math.sin(math.radians(-45)))
    v = (math.cos(math.radians(45)), math.sin(math.radians(45)))

    def P(a, b):
        return (C[0] + a * u[0] + b * v[0], C[1] + a * u[1] + b * v[1])

    pins = {1: P(HYB["pin_dx"], HYB["pin_dy"]), 2: P(-HYB["pin_dx"], HYB["pin_dy"]),
            3: P(-HYB["pin_dx"], -HYB["pin_dy"]), 4: P(HYB["pin_dx"], -HYB["pin_dy"])}
    PX, PY = (gm.feed, 0.0), (0.0, gm.feed)
    ex = HYB["pin_dx"] + 3.5
    N1, N2, X4, X3 = P(ex, HYB["pin_dy"]), P(-ex, HYB["pin_dy"]), P(ex, -HYB["pin_dy"]), P(-ex, -HYB["pin_dy"])
    S = (30.0, -13.0)
    d = (math.cos(math.radians(-45)), math.sin(math.radians(-45)))
    swap = [N1, P(ex, 4.3), P(-ex, 4.3), N2]
    g, t = [], []
    g.append(poly(chamfered(gm.panel, gm.chamfer), close=True, fill="none", stroke="#000", stroke_width=0.35))
    for a, b in (((-46, 0), (46, 0)), ((0, -46), (0, 46))):
        g.append(poly([a, b], stroke="#bbb", stroke_width=0.15, stroke_dasharray="2 1"))
    g.append(poly([(-46, -46), (46, 46)], stroke="#ddd", stroke_width=0.15, stroke_dasharray="1 1"))
    g.append(circ((0, 0), gm.tube_od / 2 + 0.1, fill="none", stroke="#000", stroke_width=0.25))
    g.append(circ((0, 0), gm.tube_od / 2, fill="none", stroke="#666", stroke_width=0.15, stroke_dasharray="1 0.5"))
    g.append(circ((0, 0), gm.bore_in / 2, fill="none", stroke="#666", stroke_width=0.15, stroke_dasharray="1 0.5"))
    t.append(text((0, -7.6), f"bore: hole {gm.tube_od + 0.2:.1f}, tube OD {gm.tube_od:.1f}, ID {gm.bore_in:.1f}"))
    t.append(text((0, -9.3), f"tube soldered to top ground; sleeve {gm.sleeve:.0f} mm below"))
    for p in gm.posts:
        g.append(circ(p, gm.post_hole / 2, fill="none", stroke="#000", stroke_width=0.25))
        g.append(circ(p, 3.5, fill="none", stroke="#999", stroke_width=0.15, stroke_dasharray="0.8 0.5"))
        t.append(text((p[0], p[1] - 4.6), f"M3 ({p[0]:.0f}, {p[1]:.0f})", 1.2))
    for ang in (56, -34, -124, 146):
        e = (48 * math.cos(math.radians(ang)), 48 * math.sin(math.radians(ang)))
        chosen = ang == -34
        g.append(circ(e, 1.2, fill="#e8b400" if chosen else "none", stroke="#e8b400" if chosen else "#aaa", stroke_width=0.3))
        off = 2.0 if e[0] > 0 else -2.0
        t.append(text((e[0] + off, e[1] - 0.5), f"egress {ang} deg" + (" (chosen)" if chosen else ""), 1.3,
                      anchor="start" if e[0] > 0 else "end", fill="#b08600" if chosen else "#888"))
    for p in (PX, PY):
        g.append(circ(p, 1.3, fill="none", stroke="#c00", stroke_width=0.15, stroke_dasharray="0.6 0.4"))
        g.append(circ(p, gm.pin_hole / 2, fill="#fff", stroke="#000", stroke_width=0.25))
    t.append(text((PX[0] + 1.8, PX[1] - 2.4), f"x probe ({gm.feed:g}, 0)", 1.3, anchor="start"))
    t.append(text((PY[0] + 2.0, PY[1] + 0.6), f"y probe (0, {gm.feed:g})", 1.3, anchor="start"))
    g.append(poly([pins[4], X4, PX], stroke="#1f77b4", stroke_width=W, stroke_linejoin="round", stroke_linecap="round"))
    g.append(poly([pins[3], X3, PY], stroke="#2ca02c", stroke_width=W, stroke_linejoin="round", stroke_linecap="round"))
    g.append(poly([pins[1], N1, S], stroke="#d62728", stroke_width=W, stroke_linejoin="round", stroke_linecap="round"))
    g.append(poly(swap, stroke="#999", stroke_width=W, stroke_linejoin="round", stroke_linecap="round", stroke_dasharray="1.2 0.8"))
    g.append(poly([pins[2], N2], stroke="#999", stroke_width=W, stroke_linecap="round"))
    L2a, L2b = P(-ex - 0.8, HYB["pin_dy"]), P(-ex - 4.0, HYB["pin_dy"])
    L1a, L1b = P(ex + 0.8, HYB["pin_dy"]), P(ex + 4.0, HYB["pin_dy"])
    g.append(poly([N2, L2a], stroke="#999", stroke_width=W, stroke_linecap="butt"))
    g.append(poly([N1, L1a], stroke="#999", stroke_width=W, stroke_linecap="butt"))
    for a, b, col in ((L2a, L2b, "#444"), (L1a, L1b, "#aaa")):
        g.append(rect((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 3.2, 1.6, -45, fill="none", stroke=col, stroke_width=0.25))
        for k in (0.6, 1.4):
            g.append(circ((b[0] + k * (b[0] - a[0]) / 3.2, b[1] + k * (b[1] - a[1]) / 3.2), 0.35, fill=col, stroke="none"))

    def link(a, b, frac, col):
        cx, cy = a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac
        g.append(rect(cx, cy, 1.0, 0.6, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), fill="#fff", stroke=col, stroke_width=0.25))

    link(pins[1], N1, 0.5, "#000")
    link(N1, swap[1], 0.4, "#777")
    g.append(rect(C[0], C[1], HYB["len"], HYB["wid"], -45, fill="none", stroke="#000", stroke_width=0.3))
    for n, p in pins.items():
        g.append(rect(p[0], p[1], HYB["pin"], HYB["pin"], -45, fill="#fff", stroke="#000", stroke_width=0.25))
        off = {1: (1.4, 0.9), 2: (-1.4, 0.9), 3: (-1.6, -0.8), 4: (1.6, -0.8)}[n]
        t.append(text((p[0] + off[0], p[1] + off[1]), str(n), 1.4))
    g.append(circ(P(5.2, 1.4), 0.35, fill="#000"))
    sc = (S[0] + 3 * d[0], S[1] + 3 * d[1])
    g.append(rect(sc[0], sc[1], 6.0, 6.0, -45, fill="none", stroke="#000", stroke_width=0.3))
    g.append(circ(S, 0.5, fill="#d62728", stroke="none"))
    g.append(circ(S, 1.3, fill="none", stroke="#c00", stroke_width=0.15, stroke_dasharray="0.6 0.4"))
    for a in (45, -135):
        for k in (1.5, 4.5):
            g.append(circ((S[0] + k * d[0] + 2.5 * math.cos(math.radians(a)), S[1] + k * d[1] + 2.5 * math.sin(math.radians(a))),
                          0.45, fill="#fff", stroke="#000", stroke_width=0.2))
    face = (S[0] + 6 * d[0], S[1] + 6 * d[1])
    E = (48 * math.cos(math.radians(-34)), 48 * math.sin(math.radians(-34)))
    g.append(poly([face, (face[0] + 4 * d[0], face[1] + 4 * d[1]), E], stroke="#e8b400", stroke_width=0.5, stroke_dasharray="1.5 0.8"))
    lx = math.dist(pins[4], X4) + math.dist(X4, PX)
    li = math.dist(pins[1], N1) + math.dist(N1, S)
    t += [text((S[0] + 1.5, S[1] + 1.5), f"SMP signal pin ({S[0]:.0f}, {S[1]:.0f})", 1.2, anchor="start"),
          text((27.0, -19.0), "SMP jack, right angle, THT, 5 legs", 1.2, anchor="end"),
          text((27.0, -20.7), "axis -45 deg, cable to the -34 deg egress", 1.2, anchor="end"),
          text((19.6, 5.2), f"pin 4 -> x probe, {lx:.1f} mm", 1.2, anchor="start", fill="#1f77b4"),
          text((-1.5, 21.5), f"pin 3 -> y probe, {lx:.1f} mm", 1.2, anchor="end", fill="#2ca02c"),
          text((31.0, -4.5), f"input, {li:.1f} mm", 1.2, anchor="start", fill="#d62728"),
          text((26.0, 29.0), "swap input trace to pin 2 (unpopulated by default)", 1.1, anchor="start", fill="#777"),
          text((5.5, 31.5), "R_L2 50R 1206 + 2 GND vias", 1.1, anchor="end", fill="#444"),
          text((31.8, 8.6), "R_L1 50R (swap)", 1.1, anchor="start", fill="#888"),
          text((23.0, 10.4), "R_in1 0R", 1.1, anchor="start"), text((29.8, 15.2), "R_in2 0R", 1.1, anchor="start", fill="#777"),
          text((32.5, 5.6), "X3C22E3-03S, centre (20, 20)", 1.4, anchor="start"),
          text((32.5, 4.0), "long axis on the 135 deg line", 1.2, anchor="start"),
          text((32.5, 2.4), "pins 1 and 4 toward -45 deg", 1.2, anchor="start")]
    notes = [f"BAC S-band cross patch – ground board, component (under) side placement – {title}",
             "Frame: x right, y up, origin = bore centre, seen from the antenna side (components shown through the board). KiCad: (x, -y).",
             f"Board {gm.panel:.0f} x {gm.panel:.0f} mm, {gm.chamfer:.0f} mm chamfers, {w50_label}. Top copper: full ground pour; mask opened {gm.tube_od + 0.2:.1f} -> 15 mm at the bore and at the post holes.",
             f"Traces {W} mm (50 ohm on {w50_label}). Both output lines identical by mirror symmetry about y = x.",
             f"Probe holes {gm.pin_hole} mm plated, pad on the component side only, 2.6 mm clearance in the top ground. Post holes {gm.post_hole:.1f} mm plated, tied to ground.",
             "Hand select (datasheet p. 2): R_in1 + R_L2 = input pin 1, load pin 2 = RHCP. R_in2 + R_L1 = input pin 2, load pin 1 = LHCP."]
    coords = [("hybrid centre", C)] + [(f"hybrid pin {n}", p) for n, p in pins.items()] + \
             [("x probe", PX), ("y probe", PY), ("pin 4 bend", X4), ("pin 3 bend", X3), ("N1 input node", N1), ("N2 load node", N2),
              ("SMP signal pin", S), ("SMP body centre", sc)] + [("post hole", p) for p in gm.posts]
    return svg_doc(g, t, notes), coords


def top_board(gm: Geometry, title: str, order_scale: float, board_label: str):
    L_order = round(gm.arm * order_scale, 1)
    L_flight = gm.arm
    g, t = [], []
    g.append(poly(chamfered(gm.panel, gm.chamfer), close=True, fill="none", stroke="#000", stroke_width=0.35))
    for a, b in (((-46, 0), (46, 0)), ((0, -46), (0, 46))):
        g.append(poly([a, b], stroke="#bbb", stroke_width=0.15, stroke_dasharray="2 1"))
    g.append(poly(cross(L_order, gm.width), close=True, fill="#f3c98a", stroke="#000", stroke_width=0.3))
    g.append(poly(cross(L_flight, gm.width), close=True, fill="none", stroke="#a0522d", stroke_width=0.25, stroke_dasharray="1.2 0.6"))
    h = L_flight / 2
    for sx in (1, -1):
        for sy in (1, -1):
            g.append(poly([(sx * h, sy * (gm.width / 2 + 0.6)), (sx * h, sy * (gm.width / 2 + 2.6))], stroke="#000", stroke_width=0.25))
            g.append(poly([(sy * (gm.width / 2 + 0.6), sx * h), (sy * (gm.width / 2 + 2.6), sx * h)], stroke="#000", stroke_width=0.25))
    t.append(text((L_order / 2 + 0.3, -gm.width / 2 - 3.2), f"arm ends: {L_order:g} as ordered (solid) | {L_flight:g} design length (dashed, silk ticks)", 1.15, anchor="end"))
    g.append(circ((0, 0), 7.5, fill="none", stroke="#a0522d", stroke_width=0.2, stroke_dasharray="0.8 0.5"))
    g.append(circ((0, 0), gm.tube_od / 2 + 0.1, fill="#fff", stroke="#000", stroke_width=0.3))
    g.append(circ((0, 0), gm.bore_in / 2, fill="none", stroke="#666", stroke_width=0.15, stroke_dasharray="1 0.5"))
    t.append(text((0, -0.5), f"hole {gm.tube_od + 0.2:.1f}", 1.2))
    t.append(text((0, -9.2), f"tube OD {gm.tube_od:g} soldered to the patch, bare ring to 15 mm", 1.1))
    for p in gm.posts:
        g.append(circ(p, gm.post_hole / 2, fill="#fff", stroke="#000", stroke_width=0.25))
        t.append(text((p[0], p[1] - 4.6), f"M3 ({p[0]:.0f}, {p[1]:.0f})", 1.2))
    for (fx, fy) in ((gm.feed, 0.0), (0.0, gm.feed)):
        g.append(circ((fx, fy), gm.pad_r, fill="none", stroke="#1f77b4", stroke_width=0.35, stroke_dasharray="1 0.5"))
        if gm.through:
            g.append(circ((fx, fy), gm.clear / 2, fill="#fff", stroke="#000", stroke_width=0.2))
            g.append(circ((fx, fy), gm.ring / 2, fill="#f3c98a", stroke="#000", stroke_width=0.2))
        g.append(circ((fx, fy), gm.pin_hole / 2, fill="#fff", stroke="#000", stroke_width=0.2))
    t.append(text((gm.feed, -4.0), f"x feed ({gm.feed:g}, 0)", 1.2))
    t.append(text((0.0, gm.feed + 3.7), f"y feed (0, {gm.feed:g})", 1.2))
    ox, oy, k = -47.0, -36.0, 3.4
    g.append(circ((ox, oy), gm.pad_r * k, fill="none", stroke="#1f77b4", stroke_width=0.4, stroke_dasharray="1.5 0.8"))
    if gm.through:
        g.append(circ((ox, oy), gm.clear / 2 * k, fill="#fff", stroke="#000", stroke_width=0.3))
        g.append(circ((ox, oy), gm.ring / 2 * k, fill="#f3c98a", stroke="#000", stroke_width=0.3))
    g.append(circ((ox, oy), gm.pin_hole / 2 * k, fill="#fff", stroke="#000", stroke_width=0.3))
    t.append(text((ox, oy + gm.pad_r * k + 1.6), f"feed detail, {k:g}x", 1.2))
    labs = [f"pad r {gm.pad_r:g} on B.Cu (dashed)"]
    if gm.through:
        labs += [f"patch clearance {gm.clear:g} dia", f"top land {gm.ring:g} dia, plated hole {gm.pin_hole:g}", f"pin {gm.pin:g}, soldered on the pad side only"]
    else:
        labs += [f"plated hole {gm.pin_hole:g}, pin {gm.pin:g}", "through-pin construction NOT in this design (feed.through_pin = false)"]
    for i, lab in enumerate(labs):
        t.append(text((-37.0, -42.5 - 1.6 * i), lab, 1.1, anchor="start", fill="#1f77b4" if i == 0 else "#000"))
    notes = [f"BAC S-band cross patch – top (patch) board – {title}",
             "Frame: x right, y up, origin = bore centre, seen from the patch (outer) side. KiCad: (x, -y); patch on F.Cu, pads on B.Cu.",
             f"Board {gm.panel:.0f} x {gm.panel:.0f} mm, {gm.chamfer:.0f} mm chamfers, {board_label}. No solder mask on either side (matches the model). ENIG.",
             f"Patch ordered at {L_order:g} x {gm.width:g} mm arms ({order_scale:g} x); trim {(L_order - L_flight) / 2:.2f} mm per arm end to the {L_flight:g} mm design length.",
             f"Feeds at ({gm.feed:g}, 0) and (0, {gm.feed:g}): pad r {gm.pad_r:g} on B.Cu, pin through a plated {gm.pin_hole:g} mm hole"
             + (f", patch cleared {gm.clear:g} mm dia, {gm.ring:g} mm top land." if gm.through else "."),
             f"Tube ring: bare copper to 15 mm. Stack: ground {gm.gb:g} + gap {gm.gap:g} + top {gm.top:g} mm; pin ~{gm.gap + gm.gb + gm.top + 1.0:.1f} mm long."]
    return svg_doc(g, t, notes)


def stack_section(gm: Geometry, title: str):
    """Side view through the bore (xz plane at y = 0): boards, gap, tube, sleeve, pin, post (projected). z is drawn 3x."""
    K = 3.0
    gb, gap, top = gm.gb * K, gm.gap * K, gm.top * K
    z_patch = gap + top
    sleeve = gm.sleeve * K
    g, t = [], []
    hb = gm.panel / 2
    g.append(f'<rect x="{-hb:.3f}" y="{-gb:.3f}" width="{gm.panel:.3f}" height="{gb:.3f}" fill="#d9e6c3" stroke="#000" stroke-width="0.12"/>')
    g.append(f'<rect x="{-hb:.3f}" y="{gap:.3f}" width="{gm.panel:.3f}" height="{top:.3f}" fill="#d9e6c3" stroke="#000" stroke-width="0.12"/>')
    g.append(poly([(-hb, 0.0), (hb, 0.0)], stroke="#c8781e", stroke_width=0.35))
    g.append(poly([(-gm.arm / 2, z_patch), (gm.arm / 2, z_patch)], stroke="#c8781e", stroke_width=0.35))
    g.append(poly([(gm.feed - gm.pad_r, gap), (gm.feed + gm.pad_r, gap)], stroke="#c8781e", stroke_width=0.45))
    r_o, r_i = gm.tube_od / 2, gm.bore_in / 2
    for sx in (1, -1):
        g.append(f'<rect x="{min(sx * r_i, sx * r_o):.3f}" y="{-sleeve:.3f}" width="{r_o - r_i:.3f}" height="{sleeve + z_patch + 0.6:.3f}" fill="#b08d57" stroke="#000" stroke-width="0.1"/>')
    g.append(f'<rect x="{gm.feed - gm.pin / 2:.3f}" y="{-gb - 2.5:.3f}" width="{gm.pin:.3f}" height="{gb + 2.5 + z_patch:.3f}" fill="#999" stroke="#000" stroke-width="0.1"/>')
    px = 43.0
    for sx in (1, -1):
        g.append(f'<rect x="{sx * px - 1.5:.3f}" y="0" width="3" height="{gap:.3f}" fill="#f2e8c6" stroke="#000" stroke-width="0.1" stroke-dasharray="0.6 0.4"/>')
    g.append(f'<rect x="26.0" y="{-gb - 2.3 * K:.3f}" width="14.2" height="{2.3 * K:.3f}" fill="#eee" stroke="#000" stroke-width="0.1"/>')
    g.append(f'<rect x="30.0" y="{-gb - 4.5 * K:.3f}" width="6" height="{4.5 * K:.3f}" fill="none" stroke="#000" stroke-width="0.1" stroke-dasharray="0.6 0.4"/>')

    def dim(x, z0, z1, label, anchor="end"):
        g.append(poly([(x, z0), (x, z1)], stroke="#333", stroke_width=0.12))
        for z in (z0, z1):
            g.append(poly([(x - 0.6, z), (x + 0.6, z)], stroke="#333", stroke_width=0.12))
        t.append(text((x - 1.0 if anchor == "end" else x + 1.0, (z0 + z1) / 2 - 0.4), label, 1.1, anchor=anchor))

    dim(-44.0, -gb, 0.0, f"ground board {gm.gb:g}")
    dim(-44.0, 0.0, gap, f"air gap {gm.gap:g}")
    dim(-44.0, gap, z_patch, f"patch board {gm.top:g}")
    dim(-52.0, -gb, z_patch, f"stack {gm.gb + gm.gap + gm.top:.2f}")
    dim(44.0, -sleeve, 0.0, f"sleeve {gm.sleeve:g}", anchor="start")
    t.append(text((0, z_patch + 2.2), f"tube OD {gm.tube_od:g}, bore {gm.bore_in:g}, soldered to patch and ground", 1.1))
    t.append(text((gm.feed + 1.2, gap / 2 - 0.4), f"pin {gm.pin:g} at x = {gm.feed:g}, through both boards", 1.0, anchor="start"))
    t.append(text((26.5, -gb - 2.3 * K - 1.6), "hybrid, SMP (underside)", 1.0, anchor="start"))
    t.append(text((px + 1.5, z_patch + 2.2), "standoff (r 43, projected)", 1.0, anchor="end"))
    notes = [f"BAC S-band cross patch – stack section through the bore (x-z plane at y = 0), z drawn 3x – {title}",
             "z up = away from the spacecraft. Ground copper on top of the ground board faces the gap; patch on the outer face of the patch board;",
             "the feed pad on its inner face; the pin passes through both boards; the tube is soldered at the ground plane and at the patch."]
    body = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-60 -28 120 62" width="1200" height="620">',
            '<rect x="-60" y="-28" width="120" height="62" fill="#fff"/>', '<g transform="scale(1,-1)">', *g, '</g>', *t]
    for i, n in enumerate(notes):
        body.append(f'<text x="-58.5" y="{28.0 + 1.8 * i:.1f}" font-size="{1.3 if i == 0 else 1.1}" {"font-weight=\"bold\"" if i == 0 else ""} {FONT}>{n}</text>')
    body.append("</svg>")
    return "\n".join(body)

def draw_all(config: Path, design: Path, out_prefix: Path, title: str = "", order_scale: float = 1.03,
             ground_stack: str = "fr4_1.0", top_label: str = "0.6 mm FR4 (proto) / 0.508 mm RO4003C (flight)") -> list[str]:
    """Write the three drawings + coordinate table for one config/design; returns the files written."""
    cfg = tomllib.loads(Path(config).read_text())
    des = json.loads(Path(design).read_text())
    gm = Geometry(cfg, des, W50[ground_stack])
    w50_label = {"fr4_1.0": "1.0 mm FR4", "ro4003c_0.813": "0.813 mm RO4003C"}[ground_stack]
    out_prefix = Path(out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    ground, coords = ground_board(gm, title, w50_label)
    top = top_board(gm, title, order_scale, top_label)
    files = {f"{out_prefix}_ground.svg": ground, f"{out_prefix}_top.svg": top, f"{out_prefix}_stack.svg": stack_section(gm, title)}
    for path, content in files.items():
        Path(path).write_text(content)
    with Path(f"{out_prefix}_coordinates.md").open("w") as fh:
        fh.write(f"# {title}\n\nFrame: x right, y up, origin at the bore centre; KiCad (x, -y).\n\n| item | x [mm] | y [mm] |\n|---|---:|---:|\n")
        for n, p in coords:
            fh.write(f"| {n} | {p[0]:.2f} | {p[1]:.2f} |\n")
    written = list(files) + [f"{out_prefix}_coordinates.md"]
    # No raster copies of the drawings: the templates embed the SVGs, and cairo's text rendering is not
    # reproducible run to run, which made every regenerate dirty the git tree.
    for path in files:
        for ext in (".png", ".webp"):
            stale = Path(path[:-4] + ext)
            if stale.exists():
                stale.unlink()
    return written
