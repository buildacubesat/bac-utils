# SPDX-License-Identifier: MIT
"""Render the v4r1 marks to PNG for the template scripts. uv run --with cairosvg python marks.py [bac-design path]"""

import sys
from pathlib import Path

import cairosvg

design = Path(sys.argv[1] if len(sys.argv) > 1 else "../../../../bac-design").resolve()
assets = design / "assets"
for name, kw in (("logo", {"output_width": 2400}), ("symbol", {"output_height": 800})):
    for color in ("black", "white"):
        cairosvg.svg2png(url=str(assets / f"bac-{name}-{color}-v4r1.svg"), write_to=f"{name}-{color}.png", **kw)
        print(f"{name}-{color}.png")
