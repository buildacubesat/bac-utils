# SPDX-License-Identifier: MIT
"""A small two-layer board: 30 × 20 mm, a GND fill on both layers with a
hole for a signal pad, one signal track across the middle, one footprint
with four pads at 0.5 mm pitch (fine pitch) and one GND via."""

from __future__ import annotations


def rect_pts(x0: float, y0: float, x1: float, y1: float) -> str:
    return f"(xy {x0} {y0}) (xy {x1} {y0}) (xy {x1} {y1}) (xy {x0} {y1})"


def fill(layer: str, pts: str) -> str:
    return f"""\t\t(filled_polygon
\t\t\t(layer "{layer}")
\t\t\t(pts
\t\t\t\t{pts}
\t\t\t)
\t\t)
"""


# a GND fill with a 4 × 4 mm island cut out around (10, 10)
GND_PTS = "(xy 1 1) (xy 29 1) (xy 29 19) (xy 1 19) (xy 1 12) (xy 8 12) (xy 8 8) (xy 12 8) (xy 12 12) (xy 1 12)"

BOARD = f"""(kicad_pcb
\t(version 20260206)
\t(generator "pcbnew")
\t(generator_version "10.0")
\t(general
\t\t(thickness 1.6)
\t)
\t(uuid "00000000-0000-0000-0000-000000000001")
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(25 "Edge.Cuts" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t)
\t(setup
\t\t(stackup
\t\t\t(layer "dielectric 1"
\t\t\t\t(type "core")
\t\t\t\t(epsilon_r 4.0)
\t\t\t)
\t\t)
\t)
\t(net 0 "")
\t(net 1 "GND")
\t(net 2 "SIG")
\t(footprint "test:Fine"
\t\t(layer "F.Cu")
\t\t(uuid "00000000-0000-0000-0000-00000000000f")
\t\t(at 22 14 90)
\t\t(property "Reference" "U1"
\t\t\t(at 0 0 0)
\t\t\t(layer "F.SilkS")
\t\t)
\t\t(fp_rect
\t\t\t(start -1.5 -1)
\t\t\t(end 1.5 1)
\t\t\t(stroke
\t\t\t\t(width 0.05)
\t\t\t\t(type default)
\t\t\t)
\t\t\t(fill no)
\t\t\t(layer "F.CrtYd")
\t\t)
\t\t(pad "1" smd rect
\t\t\t(at -0.75 0 90)
\t\t\t(size 0.3 0.8)
\t\t\t(layers "F.Cu")
\t\t\t(net 2 "SIG")
\t\t)
\t\t(pad "2" smd rect
\t\t\t(at -0.25 0 90)
\t\t\t(size 0.3 0.8)
\t\t\t(layers "F.Cu")
\t\t\t(net 2 "SIG")
\t\t)
\t\t(pad "3" smd rect
\t\t\t(at 0.25 0 90)
\t\t\t(size 0.3 0.8)
\t\t\t(layers "F.Cu")
\t\t\t(net 2 "SIG")
\t\t)
\t\t(pad "4" smd rect
\t\t\t(at 0.75 0 90)
\t\t\t(size 0.3 0.8)
\t\t\t(layers "F.Cu")
\t\t\t(net 2 "SIG")
\t\t)
\t)
\t(gr_rect
\t\t(start 0 0)
\t\t(end 30 20)
\t\t(stroke
\t\t\t(width 0.1)
\t\t\t(type default)
\t\t)
\t\t(fill no)
\t\t(layer "Edge.Cuts")
\t\t(uuid "00000000-0000-0000-0000-0000000000e0")
\t)
\t(segment
\t\t(start 1 15)
\t\t(end 29 15)
\t\t(width 0.3)
\t\t(layer "B.Cu")
\t\t(net "SIG")
\t\t(uuid "00000000-0000-0000-0000-0000000000a0")
\t)
\t(via
\t\t(at 5 5)
\t\t(size 0.6)
\t\t(drill 0.3)
\t\t(layers "F.Cu" "B.Cu")
\t\t(net "GND")
\t\t(uuid "00000000-0000-0000-0000-0000000000b0")
\t)
\t(zone
\t\t(net "GND")
\t\t(layers "F.Cu" "B.Cu")
\t\t(uuid "00000000-0000-0000-0000-0000000000c0")
\t\t(name "GND")
\t\t(polygon
\t\t\t(pts
\t\t\t\t{rect_pts(0, 0, 30, 20)}
\t\t\t)
\t\t)
{fill("F.Cu", GND_PTS)}{fill("B.Cu", GND_PTS)}\t)
)
"""
