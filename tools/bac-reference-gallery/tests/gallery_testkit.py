# SPDX-License-Identifier: MIT
"""Shared helpers for the gallery tests: the checkout's pages, a browser if one exists, the contrast audit."""

from __future__ import annotations

import os
import shutil
import struct
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1]
PAGES = [TOOL_DIR / "index.html", *sorted((TOOL_DIR / "examples").glob("*.html"))]


def _browser() -> Path | None:
    """A Chromium for the browser tests: BAC_CHROMIUM_PATH as the session started, else Playwright's."""
    override = os.environ.get("BAC_CHROMIUM_PATH")
    if override and Path(override).is_file():
        return Path(override)
    try:
        from bac_reference_gallery.browser import managed_path

        return managed_path()
    except Exception:  # noqa: BLE001 – no Playwright driver or no download: the browser tests skip
        return None


BROWSER = _browser()
needs_browser = pytest.mark.skipif(BROWSER is None, reason="no Chromium (set BAC_CHROMIUM_PATH or run --init)")


def copy_gallery(dest: Path) -> Path:
    """A copy of the checkout's gallery pages, for tests that change them."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "css", "assets", "examples"):
        src = TOOL_DIR / name
        if src.is_dir():
            shutil.copytree(src, dest / name)
        else:
            shutil.copy2(src, dest / name)
    return dest


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    return struct.unpack(">II", data[16:24])


# WCAG 2.x contrast of every visible text element against its composited background.
# SVG text is measured by its fill; aria-hidden decoration is skipped; large text
# (24 px, or 18.66 px bold) needs 3:1, everything else 4.5:1.
CONTRAST_JS = """() => {
  function parse(c) {
    const m = c && c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  }
  function lum(c) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  function blend(top, bottom) {
    const a = top.a;
    return {r: top.r * a + bottom.r * (1 - a), g: top.g * a + bottom.g * (1 - a), b: top.b * a + bottom.b * (1 - a), a: 1};
  }
  function background(el) {
    const stack = [];
    for (let e = el; e; e = e.parentElement) {
      const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; }
    }
    let base = {r: 255, g: 255, b: 255, a: 1};
    for (let i = stack.length - 1; i >= 0; i--) base = blend(stack[i], base);
    return base;
  }
  const failures = [];
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!node.textContent.trim()) continue;
    const el = node.parentElement;
    if (seen.has(el)) continue;
    seen.add(el);
    if (el.closest('[aria-hidden="true"]')) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    let opacity = 1;
    for (let e = el; e; e = e.parentElement) opacity *= Number(getComputedStyle(e).opacity);
    const raw = parse(el instanceof SVGElement ? cs.fill : cs.color);
    if (!raw) continue;
    const bg = background(el);
    const fg = blend({...raw, a: raw.a * opacity}, bg);
    const l1 = lum(fg), l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const size = parseFloat(cs.fontSize), weight = parseInt(cs.fontWeight, 10);
    const need = (size >= 24 || (size >= 18.66 && weight >= 700)) ? 3 : 4.5;
    if (ratio < need) failures.push(`${node.textContent.trim().slice(0, 40)} – ${ratio.toFixed(2)}:1, needs ${need}:1`);
  }
  return failures;
}"""


# Everything on a board ends above its footer note (or inside the board when it has none), after
# clipping by any ancestor that hides overflow; the board itself does not scroll, and no card's
# content spills out of its box.
LAYOUT_JS = """() => {
  const board = document.querySelector('.board');
  if (!board) return [];
  const problems = [];
  if (board.scrollHeight > board.clientHeight + 1) {
    problems.push(`board content is ${board.scrollHeight} px tall in ${board.clientHeight} px`);
  }
  for (const card of board.querySelectorAll('.card, .ps-card, .ps-case, .ps-well')) {
    if (card.scrollHeight > card.clientHeight + 1) {
      const label = (card.textContent || '').trim().slice(0, 30);
      problems.push(`${label}: content ${card.scrollHeight} px in a ${card.clientHeight} px card`);
    }
  }
  const footer = board.querySelector('.footer-note');
  const limit = footer ? footer.getBoundingClientRect().top : board.getBoundingClientRect().bottom;
  for (const el of board.querySelectorAll('*')) {
    if (footer && (el === footer || footer.contains(el))) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    let bottom = r.bottom;
    for (let a = el.parentElement; a && a !== board; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (cs.overflowY !== 'visible') bottom = Math.min(bottom, a.getBoundingClientRect().bottom);
    }
    if (bottom > limit + 0.5) {
      const label = (el.textContent || '').trim().slice(0, 30) || el.tagName.toLowerCase();
      problems.push(`${label} ends at ${Math.round(bottom)}, limit ${Math.round(limit)}`);
    }
  }
  return problems.slice(0, 8);
}"""
