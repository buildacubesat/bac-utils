# SPDX-License-Identifier: MIT
"""The Rocinante marks – the flight software stack's horse, ring and wordmark.

The geometry is the vector artwork of the original Krita file (Rocinante_Logo.kra, 245.76 pt
canvas) carried over point by point and scaled by 5, with the ring made a true circle and its
three gaps defined by angle instead of cut-out shapes. The wordmark is set in Nunito and the
subtitle in IBM Plex Mono as in the original, outlined.
"""

from __future__ import annotations

import math
from pathlib import Path

from . import wordmark

VERSION = "v2r1"
SCALE = 5
CANVAS = 550  # the symbol's square canvas
CENTRE = (122.7712, 96.78)  # ring centre in the source, mapped to the canvas centre
RING_R = 48.27 * SCALE  # centre-line radius
RING_STROKE = 11
GAPS = ((-80, -56), (97, 117), (155, 167))  # degrees, SVG orientation (clockwise from 3 o'clock)

# the head: a closed polygon with the jaw as two cubic curves, the eye as a hole, the ear separate
HEAD = (
    "M77.310 115.860L117.915 72.360L131.370 60.210L148.920 49.635L138.255 65.295L125.520 73.710L127.275 73.755"
    "L137.895 86.085L143.760 108.585L137.771 113.917L134.273 113.951L127.890 105.420L115.410 98.610"
    "L102.345 128.295L108.341 143.921C102.730 142.595 96.001 138.742 88.154 132.362"
    "C82.357 126.190 78.742 120.689 77.310 115.860Z"
)
EYE = "M125.550 85.710L131.520 88.680L132.720 93.090L127.500 90.570Z"
EAR = "M132.150 73.800L139.590 69.240L153.360 63.780L144.780 73.050L134.700 76.710Z"

# wordmark, as in the source: Nunito 24 pt with 3 pt tracking, Plex Mono 7 pt with 2 pt tracking;
# the rules either side of the subtitle fill out to the word's width
WORD = "ROCINANTE"
WORD_WEIGHT = 350
WORD_SIZE = 24 * SCALE
WORD_TRACKING = 3 * SCALE
SUB = "CUBESAT SOFTWARE STACK"
SUB_WEIGHT = 400
SUB_SIZE = 7 * SCALE
SUB_TRACKING = 2 * SCALE
SUB_GAP = 16.4 * SCALE  # wordmark baseline to subtitle baseline
LOGO_GAP = 32 * SCALE  # ring bottom to wordmark baseline

COLORS = {"black": "#000000", "white": "#ffffff", "currentcolor": "currentColor"}
TWO_TONE = {"head": "#1F1F1F", "ring": "#004C8B"}  # --text-strong for head and word, --bac-blue for ring and subtitle


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _map(path: str, ox: float, oy: float) -> str:
    """Scale source coordinates onto the canvas with the ring centre at (ox, oy)."""
    import re

    def pt(m: re.Match) -> str:
        x = (float(m.group(1)) - CENTRE[0]) * SCALE + ox
        y = (float(m.group(2)) - CENTRE[1]) * SCALE + oy
        return f"{_f(x)} {_f(y)}"

    return re.sub(r"(-?[\d.]+) (-?[\d.]+)", pt, path)


def ring_path(cx: float, cy: float) -> str:
    """Three arcs between the gaps, clockwise."""
    gaps = sorted(GAPS)
    parts = []
    for i, (_, start) in enumerate(gaps):
        end = gaps[(i + 1) % len(gaps)][0]
        if end <= start:
            end += 360
        a0, a1 = math.radians(start), math.radians(end)
        x0, y0 = cx + RING_R * math.cos(a0), cy + RING_R * math.sin(a0)
        x1, y1 = cx + RING_R * math.cos(a1), cy + RING_R * math.sin(a1)
        large = 1 if end - start > 180 else 0
        parts.append(f"M{_f(x0)} {_f(y0)} A{_f(RING_R)} {_f(RING_R)} 0 {large} 1 {_f(x1)} {_f(y1)}")
    return " ".join(parts)


def symbol_group(head_color: str, ring_color: str, ox: float = 0, oy: float = 0) -> str:
    cx, cy = ox + CANVAS / 2, oy + CANVAS / 2
    return (
        '  <g id="symbol">\n'
        f'    <path id="ring" d="{ring_path(cx, cy)}" fill="none" stroke="{ring_color}"'
        f' stroke-width="{RING_STROKE}"/>\n'
        f'    <path id="head" fill-rule="evenodd" fill="{head_color}" d="{_map(HEAD, cx, cy)} {_map(EYE, cx, cy)}"/>\n'
        f'    <path id="ear" fill="{head_color}" d="{_map(EAR, cx, cy)}"/>\n'
        "  </g>\n"
    )


def wordmark_group(fonts_dir: Path, word_color: str, sub_color: str, cx: float, baseline: float) -> tuple[str, float]:
    """ROCINANTE centred on cx with the subtitle and its rules under it; returns (group, width)."""
    from fontTools.ttLib import TTFont

    nunito = wordmark.load(fonts_dir, WORD_WEIGHT)
    d1, w1 = wordmark.line(nunito, WORD, WORD_SIZE, 0, 0, WORD_TRACKING)
    mono = TTFont(fonts_dir / wordmark.MONO_FONT_FILE)
    frag, width = wordmark.subtitle(mono, SUB, SUB_SIZE, SUB_TRACKING / SUB_SIZE, cx, baseline + SUB_GAP, w1, sub_color)
    return (
        '  <g id="wordmark">\n'
        f'    <path id="word" fill="{word_color}" transform="translate({_f(cx - w1 / 2)} {_f(baseline)})" d="{d1}"/>\n'
        + frag
        + "  </g>\n"
    ), width


def colours(variant: str) -> tuple[str, str]:
    """(head and word, ring and subtitle) for a colour variant."""
    if variant == "colour":
        return TWO_TONE["head"], TWO_TONE["ring"]
    return COLORS[variant], COLORS[variant]


def symbol_svg(variant: str, wrap) -> str:
    a, b = colours(variant)
    return wrap(
        "symbol", symbol_group(a, b), CANVAS, CANVAS, _construction(variant), brand="Rocinante", version=VERSION
    )


def wordmark_svg(fonts_dir: Path, variant: str, wrap) -> str:
    a, b = colours(variant)
    pad = 40
    g, w = wordmark_group(fonts_dir, a, b, 0, 0)
    cap = WORD_SIZE * 0.705
    h = cap + SUB_GAP + pad
    body = f'  <g transform="translate({_f(w / 2 + pad)} {_f(pad + cap)})">\n{g}  </g>\n'
    return wrap("wordmark", body, w + 2 * pad, h + pad, _construction(variant), brand="Rocinante", version=VERSION)


def logo_svg(fonts_dir: Path, variant: str, wrap) -> str:
    """The stacked lockup, as the original: symbol above the wordmark, centred."""
    a, b = colours(variant)
    g, w = wordmark_group(fonts_dir, a, b, 0, 0)
    width = max(CANVAS, w + 80)
    cx = width / 2
    baseline = CANVAS / 2 + RING_R + LOGO_GAP
    height = baseline + SUB_GAP + 25
    body = symbol_group(a, b, cx - CANVAS / 2, 0) + f'  <g transform="translate({_f(cx)} {_f(baseline)})">\n{g}  </g>\n'
    return wrap("logo", body, width, height, _construction(variant), brand="Rocinante", version=VERSION)


def _construction(variant: str) -> str:
    c = (
        f"Head polygon and ear from the original vector artwork at scale {SCALE}, ring radius {_f(RING_R)}"
        f" stroke {RING_STROKE} with three gaps; Nunito {WORD_WEIGHT} and IBM Plex Mono {SUB_WEIGHT}, outlined."
    )
    if variant == "colour":
        c += (
            f" Two-tone in brand colours: {TWO_TONE['head']} for head and word,"
            f" {TWO_TONE['ring']} for ring and subtitle."
        )
    return c
