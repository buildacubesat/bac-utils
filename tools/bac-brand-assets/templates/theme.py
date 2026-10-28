# SPDX-License-Identifier: MIT
"""Write the theme colours slides.js records in theme.json into a deck pptxgenjs wrote.

pptxgenjs sets the theme fonts but hard-codes Office's palette, so scheme colours resolve to
Office blue and orange until the deck's own colours are written into ppt/theme/theme1.xml.
python theme.py bac-slides-template-v1r1.pptx
"""

import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

SLOTS = (
    "dk1",
    "lt1",
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "hlink",
    "folHlink",
)

deck = Path(sys.argv[1])
theme = json.loads(Path("theme.json").read_text(encoding="utf-8"))
name = theme["name"].replace("&", "&amp;").replace('"', "&quot;")
scheme = (
    f'<a:clrScheme name="{name}">'
    + "".join(f'<a:{k}><a:srgbClr val="{theme["colors"][k].upper()}"/></a:{k}>' for k in SLOTS)
    + "</a:clrScheme>"
)

tmp = Path(tempfile.mkdtemp()) / deck.name
with zipfile.ZipFile(deck) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
    for item in src.infolist():
        data = src.read(item.filename)
        if item.filename == "ppt/theme/theme1.xml":
            xml = data.decode("utf-8")
            xml, n = re.subn(r"<a:clrScheme\b[\s\S]*?</a:clrScheme>", lambda _: scheme, xml, count=1)
            if not n:
                raise SystemExit("ppt/theme/theme1.xml has no <a:clrScheme>; nothing was changed.")
            xml = re.sub(r'(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"', lambda m: f'{m.group(1)}{name}"', xml)
            data = xml.encode("utf-8")
        dst.writestr(item, data)
shutil.move(tmp, deck)
print(f"theme written: {deck}")
