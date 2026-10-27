# SPDX-License-Identifier: MIT
"""Render the v4r1 marks to PNG for the template scripts and record their pixel sizes.

uv run --with cairosvg python marks.py [bac-design path] [gallery assets path]
Writes logo-, logo-tagline- and symbol-{black,white}.png, two sample illustrations and marks.json; the scripts take the
aspect ratio from marks.json, never from a constant, so a new mark revision cannot distort it.
"""

import json
import re
import sys
from pathlib import Path

import cairosvg

design = Path(sys.argv[1] if len(sys.argv) > 1 else "../../../../bac-design").resolve()
assets = design / "assets"
sizes = {}
for name, kw in (("logo", {"output_width": 2400}), ("logo-tagline", {"output_width": 2400}), ("symbol", {"output_height": 800})):
    for color in ("black", "white"):
        svg = assets / f"bac-{name}-{color}-v4r1.svg"
        m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg.read_text(encoding="utf-8"))
        vw, vh = float(m.group(1)), float(m.group(2))
        if "output_width" in kw:
            w, h = kw["output_width"], round(kw["output_width"] * vh / vw)
        else:
            w, h = round(kw["output_height"] * vw / vh), kw["output_height"]
        cairosvg.svg2png(url=str(svg), write_to=f"{name}-{color}.png", output_width=w, output_height=h)
        sizes[name] = {"width": w, "height": h, "viewBox": [vw, vh]}
        print(f"{name}-{color}.png {w}×{h}")
# Two gallery illustrations for the sample slides (the slots are for hardware photography).
gallery = Path(sys.argv[2] if len(sys.argv) > 2 else "../../bac-reference-gallery/assets").resolve()
for name in ("led-board", "cubesat-wireframe"):
    svg = gallery / f"{name}.svg"
    if svg.exists():
        cairosvg.svg2png(url=str(svg), write_to=f"sample-{name}.png", output_width=1600)
        print(f"sample-{name}.png")
# The kicker: the short BAC Yellow dash before an eyebrow (18 × 4 px, rounded 2, Identity Guide §4.1).
cairosvg.svg2png(bytestring=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 4"><rect width="18" height="4" rx="2" fill="#F7D400"/></svg>', write_to="kicker.png", output_width=360)
print("kicker.png")
Path("marks.json").write_text(json.dumps(sizes, indent=2) + "\n", encoding="utf-8")
print("marks.json")
