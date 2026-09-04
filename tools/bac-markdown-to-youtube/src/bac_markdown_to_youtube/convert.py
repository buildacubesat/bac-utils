# SPDX-License-Identifier: MIT
"""Markdown to YouTube description markup.

YouTube renders three inline styles in a video description: ``*bold*``,
``_italic_`` and ``-strikethrough-``. They nest (``*_both_*``), but a
delimiter only counts when whitespace or the line boundary surrounds the
styled span – ``*bold*,`` shows the asterisks. Headings, links, code and
block quotes have no equivalent and are flattened to text.

The conversion runs in passes. Every span that has reached its final form
is parked behind a placeholder so that a later pass cannot match it again
(the old script's italic pass re-matched the output of its bold pass, which
turned ``**bold**`` into ``_bold_``). Placeholders are restored at the end,
and styled spans get the surrounding whitespace YouTube requires.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["convert"]

# Private-use characters bracket a placeholder index: they never occur in text.
_OPEN = "\ue000"
_CLOSE = "\ue001"
_PLACEHOLDER = re.compile(f"{_OPEN}(\\d+){_CLOSE}")

_WHITESPACE = set(" \t\n")
_DELIMITERS = "*_-"

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n(.*?)^[ \t]*\1[ \t]*$\n?", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!~<>|])")
_LINK = re.compile(r"!?\[([^\]\n]+)\]\(\s*<?([^\s)>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
_BARE_URL = re.compile(r"(?<![\w/])https?://[^\s<>]+")
_URL_TRAIL = ".,;:!?)"

# Asterisk emphasis may not touch a letter, digit or another asterisk on the
# outside (so ``2*3*4`` stays arithmetic); underscore emphasis may not touch a
# word character at all (so ``snake_case_name`` stays a name).
_STAR_L, _STAR_R = r"(?<![^\W_])(?<!\*)", r"(?![^\W_])(?!\*)"
_LOW_L, _LOW_R = r"(?<![\w])", r"(?![\w])"
_BOLD_ITALIC_STAR = re.compile(_STAR_L + r"\*\*\*(?=[^\s*])([^\n]+?)(?<=[^\s*])\*\*\*" + _STAR_R)
_BOLD_ITALIC_LOW = re.compile(_LOW_L + r"___(?=[^\s_])([^\n]+?)(?<=[^\s_])___" + _LOW_R)
_BOLD_STAR = re.compile(_STAR_L + r"\*\*(?=[^\s*])([^\n]+?)(?<=[^\s*])\*\*" + _STAR_R)
_BOLD_LOW = re.compile(_LOW_L + r"__(?=[^\s_])([^\n]+?)(?<=[^\s_])__" + _LOW_R)
_ITALIC_STAR = re.compile(_STAR_L + r"\*(?=[^\s*])([^\n]+?)(?<=[^\s*])\*" + _STAR_R)
_ITALIC_LOW = re.compile(_LOW_L + r"_(?=[^\s_])([^\n]+?)(?<=[^\s_])_" + _LOW_R)
_STRIKE = re.compile(r"~~(?=\S)([^\n]+?)(?<=\S)~~")

_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
_BULLET = re.compile(r"^([ \t]*)[*+][ \t]+", re.MULTILINE)
_QUOTE = re.compile(r"^[ \t]{0,3}(?:>[ \t]?)+", re.MULTILINE)
_BREAK = re.compile(r"<br[ \t]*/?>", re.IGNORECASE)
# Only tags HTML actually has are dropped; ``Vec<u8>`` or ``<placeholder>`` stay.
_TAG_NAMES = (
    "a|abbr|b|blockquote|br|center|cite|code|del|details|div|em|font|h[1-6]|hr|i|img|ins|kbd|li|mark|ol|p|pre|"
    "s|small|span|strike|strong|sub|summary|sup|table|tbody|td|th|thead|tr|u|ul"
)
_TAG = re.compile(rf"</?(?:{_TAG_NAMES})(?:[ \t][^<>]*)?/?>", re.IGNORECASE)


@dataclass
class _Store:
    """Parked spans: ``(text, styled)``. Styled spans get whitespace on restore."""

    items: list[tuple[str, bool]] = field(default_factory=list)

    def park(self, text: str, *, styled: bool = False) -> str:
        self.items.append((text, styled))
        return f"{_OPEN}{len(self.items) - 1}{_CLOSE}"

    def unwrap_bold(self, text: str) -> str:
        """Bold placeholders inside ``text`` lose their asterisks (bold-italic keeps its italics)."""

        def strip(m: re.Match[str]) -> str:
            parked, styled = self.items[int(m.group(1))]
            if styled and parked.startswith("*") and parked.endswith("*"):
                inner = parked[1:-1]
                return self.park(inner, styled=True) if inner.startswith("_") else inner
            return m.group(0)

        return _PLACEHOLDER.sub(strip, text)

    def restore(self, text: str) -> str:
        """Replace every placeholder, inserting the whitespace a styled span needs.

        A styled span needs whitespace (or the line boundary) on both sides.
        Inside a parked span the only other neighbour allowed is the enclosing
        span's own delimiter, so nested spans are restored while their parent
        is, with the parent's delimiters known.
        """
        return self._restore(text, enclosing="")

    def _restore(self, text: str, *, enclosing: str) -> str:
        result = ""
        last = 0
        for m in _PLACEHOLDER.finditer(text):
            parked, styled = self.items[int(m.group(1))]
            result += text[last : m.start()]
            after = text[m.end() :]
            if styled:
                own = parked[0] if parked and parked[0] in _DELIMITERS else ""
                parked = self._restore(parked, enclosing=own)
                prev_ok = not result or result[-1] in _WHITESPACE or bool(enclosing and result.strip(enclosing) == "")
                next_ok = not after or after[0] in _WHITESPACE or bool(enclosing and after.strip(enclosing) == "")
                if not prev_ok:
                    parked = " " + parked
                if not next_ok:
                    parked = parked + " "
            else:
                parked = self._restore(parked, enclosing="")
            result += parked
            last = m.end()
        return result + text[last:]


def _link(store: _Store, m: re.Match[str]) -> str:
    text, url = m.group(1), m.group(2)
    separator = ":" if text[-1].isalnum() else ""
    return f"{text}{separator} {store.park(url)}"


def _bare_url(store: _Store, m: re.Match[str]) -> str:
    url = m.group(0)
    trail = ""
    while url and url[-1] in _URL_TRAIL:
        trail = url[-1] + trail
        url = url[:-1]
    return store.park(url) + trail


def _heading(store: _Store, m: re.Match[str]) -> str:
    content = store.unwrap_bold(m.group(1).strip())
    return store.park(f"*{content}*", styled=True)


def convert(markdown: str) -> str:
    """Return the YouTube description text for ``markdown``."""
    store = _Store()
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")

    # Verbatim regions first, so nothing inside them is touched.
    text = _FENCE.sub(lambda m: store.park(m.group(2).rstrip("\n")) + "\n", text)
    text = _COMMENT.sub("", text)
    text = _INLINE_CODE.sub(lambda m: store.park(m.group(1)), text)
    text = _ESCAPE.sub(lambda m: store.park(m.group(1)), text)

    # Block-quote markers go early so the quoted text is converted like any other.
    text = _QUOTE.sub("", text)

    # URLs are parked before the emphasis passes: underscores in a path must
    # not become italics.
    text = _LINK.sub(lambda m: _link(store, m), text)
    text = _AUTOLINK.sub(lambda m: store.park(m.group(1)), text)
    text = _BARE_URL.sub(lambda m: _bare_url(store, m), text)

    # Inline styles, strongest first. Each result is parked immediately.
    for pattern, template in (
        (_BOLD_ITALIC_STAR, "*_{}_*"),
        (_BOLD_ITALIC_LOW, "*_{}_*"),
        (_BOLD_STAR, "*{}*"),
        (_BOLD_LOW, "*{}*"),
        (_ITALIC_STAR, "_{}_"),
        (_ITALIC_LOW, "_{}_"),
        (_STRIKE, "-{}-"),
    ):
        text = pattern.sub(lambda m, t=template: store.park(t.format(m.group(1)), styled=True), text)

    # Block structure: headings become bold lines, bullets use a hyphen so a
    # leading asterisk cannot be read as emphasis.
    text = _HEADING.sub(lambda m: _heading(store, m), text)
    text = _BULLET.sub(r"\1- ", text)

    # HTML shows literally on YouTube; a line break tag becomes a newline.
    text = _BREAK.sub("\n", text)
    text = _TAG.sub("", text)

    return store.restore(text)
