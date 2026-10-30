# SPDX-License-Identifier: MIT
"""Take the v4r1 marks for the template scripts from bac-design and record their pixel sizes.

uv run --with cairosvg python marks.py [bac-design path] [gallery assets path]
Copies logo-{black,white}, logo-tagline-white and symbol-{black,white}.png from bac-design assets/png/ (the 2048 px
renderings bac-brand-assets writes), renders the kicker and two sample illustrations, and writes
marks.json; the scripts take every aspect ratio from marks.json, never from a constant, so a new
mark revision cannot distort it.
"""

import json
import shutil
import struct
import sys
from pathlib import Path

import cairosvg

VERSION = "v4r1"
SIZE = 2048

design = Path(sys.argv[1] if len(sys.argv) > 1 else "../../../../bac-design").resolve()
png_dir = design / "assets" / "png"


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from the PNG's IHDR chunk."""
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path} is not a PNG.")
    return struct.unpack(">II", head[16:24])


# The five marks the letterhead and the slides place.
MARKS = (("logo", "black"), ("logo", "white"), ("logo-tagline", "white"), ("symbol", "black"), ("symbol", "white"))

sizes = {}
for name, color in MARKS:
    source = png_dir / f"bac-{name}-{color}-{VERSION}-{SIZE}.png"
    if not source.is_file():
        raise SystemExit(f"{source} is missing. Run bac-brand-assets in bac-utils first.")
    shutil.copyfile(source, f"{name}-{color}.png")
    w, h = png_size(source)
    sizes[name] = {"width": w, "height": h, "source": f"assets/png/{source.name}"}
    print(f"{name}-{color}.png {w}×{h} (from {source.name})")

# Two gallery illustrations for the sample slides (the slots are for hardware photography).
gallery = Path(sys.argv[2] if len(sys.argv) > 2 else "../../bac-reference-gallery/assets").resolve()
for name in ("led-board", "cubesat-wireframe"):
    svg = gallery / f"{name}.svg"
    if svg.exists():
        cairosvg.svg2png(url=str(svg), write_to=f"sample-{name}.png", output_width=1600)
        print(f"sample-{name}.png")
# The kicker: the short BAC Yellow dash before an eyebrow (18 × 4 px, rounded 2, Identity Guide §4.1).
cairosvg.svg2png(
    bytestring=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 4"><rect width="18" height="4" rx="2" fill="#F7D400"/></svg>',  # noqa: E501
    write_to="kicker.png",
    output_width=360,
)
print("kicker.png")
Path("marks.json").write_text(json.dumps(sizes, indent=2) + "\n", encoding="utf-8")
print("marks.json")
