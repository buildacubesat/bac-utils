# SPDX-License-Identifier: MIT
"""Render the Mission surfaces the slides template places as images.

uv run --with playwright python surfaces.py
Writes hero-bg.png (the dark hero: --space-ink with nebula light, a restrained starfield and
orbital rings, 16:9 at 1920 × 1080) and viewport.png (the recessed viewport: gridded dark panel,
teal-tinted border, inner glow, 1320 × 990). The CSS is the BAC Reference Gallery's product-sheet
hero and viewport (Identity Guide §6–§7); pptxgenjs cannot draw inset glows or gradients of this
kind, so the surfaces are rendered once here and the layouts carry the pixels.
Needs a Chromium – the one bac-reference-gallery --init installs is enough.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

HERO = """<!doctype html><meta charset="utf-8"><style>
html,body{margin:0}
.hero{width:1920px;height:1080px;position:relative;overflow:hidden;
  background:
    radial-gradient(ellipse at 72% 8%, rgba(122,90,248,.38) 0, rgba(122,90,248,.08) 17%, transparent 33%),
    radial-gradient(ellipse at 84% 46%, rgba(14,149,148,.18) 0, transparent 28%),
    radial-gradient(ellipse at 10% 95%, rgba(14,149,148,.14) 0, transparent 30%),
    radial-gradient(circle at 52% 22%, rgba(255,255,255,.85) 0 1.4px, transparent 1.9px),
    radial-gradient(circle at 19% 64%, rgba(255,255,255,.65) 0 1.4px, transparent 1.9px),
    radial-gradient(circle at 88% 76%, rgba(255,255,255,.7) 0 1.4px, transparent 1.9px),
    #171320;}
.hero::before{content:"";position:absolute;inset:0;opacity:.22;
  background-image:
    radial-gradient(circle, rgba(255,255,255,.95) 0 1.1px, transparent 1.7px),
    radial-gradient(circle, rgba(255,255,255,.55) 0 1px, transparent 1.5px),
    radial-gradient(circle, rgba(255,255,255,.4) 0 .9px, transparent 1.4px);
  background-size:233px 181px, 157px 263px, 311px 127px;background-position:17px 31px, 61px 119px, 131px 73px;}
.ring{position:absolute;border:1.5px solid rgba(143,135,158,.26);border-radius:50%;transform:rotate(-12deg)}
.r1{width:1120px;height:470px;right:-220px;top:-150px}
.r2{width:1120px;height:470px;right:-220px;top:-20px;border-color:rgba(143,135,158,.14)}
.r3{width:1120px;height:470px;right:-220px;top:112px;border-color:rgba(143,135,158,.08)}
</style><div class="hero"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div></div>"""

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
    shot(page, HERO, ".hero", "hero-bg.png")
    shot(page, VIEWPORT, ".vp", "viewport.png", omit_bg=True)
    browser.close()
Path("hero-bg.png").stat()
