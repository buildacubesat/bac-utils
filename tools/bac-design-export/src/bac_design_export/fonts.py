# SPDX-License-Identifier: MIT
"""The faces a document uses, from the self-hosted files in bac-design ``fonts/``.

Nunito Sans ships as one variable font (YTLC, opsz, wdth, wght). PDF renderers pick a
variable font's default instance unreliably, so each weight the stylesheet asks for is cut
as a static instance once and cached; IBM Plex Mono ships as static faces already.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from bac_common.errors import ConfigError

SANS = "NunitoSans[YTLC,opsz,wdth,wght].ttf"
SANS_ITALIC = "NunitoSans-Italic[YTLC,opsz,wdth,wght].ttf"
MONO = {400: "IBMPlexMono-Regular.ttf", 500: "IBMPlexMono-Medium.ttf", 600: "IBMPlexMono-SemiBold.ttf"}
MONO_ITALIC = "IBMPlexMono-Italic.ttf"
# Weights the print stylesheet uses: 400 body, 500 headings, 600 and 700 for <strong> and table heads.
SANS_WEIGHTS = (400, 500, 600, 700)
OPSZ = 10  # text optical size: print body sits at 9.5–10 pt
# Nunito Sans has no arrows or box drawing; IBM Plex Mono has them, so it fills in for exactly those
# code points under the alias "BAC Symbols" (no font of its own, the shipped Plex Mono files).
# ✓ and ✗ are left to the system font: no BAC font has ✗, and the pair should match (Identity Guide §8,
# to be decided).
SYMBOLS = "BAC Symbols"
SYMBOL_RANGE = "U+2190-21FF, U+2500-259F"


@dataclass(frozen=True)
class Face:
    family: str
    weight: int
    style: str
    path: Path


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "bac-design-export" / "fonts"


def _instance(source: Path, weight: int, italic: bool) -> Path:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    out = cache_dir() / f"NunitoSans-{'Italic-' if italic else ''}{weight}-opsz{OPSZ}-{digest}.ttf"
    if not out.is_file():
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont

        font = TTFont(source)
        static = instantiateVariableFont(font, {"wght": weight, "opsz": OPSZ, "wdth": 100, "YTLC": 500})
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".part")
        static.save(tmp)
        tmp.replace(out)
    return out


def faces(fonts: Path) -> list[Face]:
    """Every face the stylesheet declares, Nunito Sans cut to static instances."""
    needed = [SANS, SANS_ITALIC, MONO_ITALIC, *MONO.values()]
    missing = [name for name in needed if not (fonts / name).is_file()]
    if missing:
        raise ConfigError(f"Missing in {fonts}: {', '.join(missing)}", "The fonts come from the bac-design checkout.")
    out = [Face("Nunito Sans", w, "normal", _instance(fonts / SANS, w, False)) for w in SANS_WEIGHTS]
    out.append(Face("Nunito Sans", 400, "italic", _instance(fonts / SANS_ITALIC, 400, True)))
    out += [Face("IBM Plex Mono", w, "normal", fonts / name) for w, name in MONO.items()]
    out.append(Face("IBM Plex Mono", 400, "italic", fonts / MONO_ITALIC))
    return out


def font_face_css(items: list[Face]) -> str:
    rules = [
        f"@font-face {{ font-family: '{f.family}'; font-weight: {f.weight}; font-style: {f.style}; "
        f"src: url('{f.path.as_uri()}'); }}"
        for f in items
    ]
    for f in items:
        if f.family == "IBM Plex Mono" and f.style == "normal" and f.weight in (400, 500):
            rules.append(
                f"@font-face {{ font-family: '{SYMBOLS}'; font-weight: {f.weight}; "
                f"src: url('{f.path.as_uri()}'); unicode-range: {SYMBOL_RANGE}; }}"
            )
    return "\n".join(rules)
