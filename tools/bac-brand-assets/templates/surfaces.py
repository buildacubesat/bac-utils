# SPDX-License-Identifier: MIT
"""Render the recessed viewport the Mission title slide places as an image.

uv run --with playwright python surfaces.py
Writes viewport.png (gridded dark panel, teal-tinted border, inner glow, 1320 × 990), the
BAC Reference Gallery's product-sheet viewport (Identity Guide §7, surface 1). pptxgenjs cannot
draw inset glows, so the surface is rendered once here and the layout carries the pixels. The
Mission backdrop itself is nebula.jpg, the nebula of the Tooldance media kit (2026-10).
Needs a Chromium – the one bac-reference-gallery --init installs is enough.
"""

from playwright.sync_api import sync_playwright

VIEWPORT = """<!doctype html><meta charset="utf-8"><style>
html,body{margin:0;background:transparent}
.vp{width:1320px;height:990px;position:relative;overflow:hidden;box-sizing:border-box;
  border:2px solid rgba(14,149,148,.42);border-radius:20px;
  background:
    linear-gradient(rgba(14,149,148,.08) 2px, transparent 2px),
    linear-gradient(90deg, rgba(14,149,148,.08) 2px, transparent 2px), #101421;
  background-size:48px 48px;
  box-shadow:inset 0 0 56px rgba(14,149,148,.16), inset 0 0 136px rgba(36,27,63,.30);}
.vp::before{content:"";position:absolute;inset:22px;border:2px solid rgba(105,208,225,.24);border-radius:20px}
.vp::after{content:"";position:absolute;left:48px;right:48px;bottom:58px;height:2px;
  background:linear-gradient(90deg,rgba(105,208,225,.5) 0 20%,transparent 20% 100%)}
</style><div class="vp"></div>"""


def shot(page, html, selector, out, omit_bg=False):
    page.set_content(html)
    page.locator(selector).screenshot(path=out, omit_background=omit_bg)
    print(out)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    shot(page, VIEWPORT, ".vp", "viewport.png", omit_bg=True)
    browser.close()
