# SPDX-License-Identifier: MIT
"""The BAC SKU scheme (Project & Tooling Guide §2.9) as a parser.

::

    bac-<cat>-<sub>-<name>-<versionstring>[-<variant>]

Every field is lowercase. Hyphens separate fields and the words of a name;
a name may carry dots for legibility (``1.5u``). The version string is the
hardware one, ``v<version>r<revision>[.<patch>]``, and anchors the parse:
whatever follows it is the optional store variant (``b``, ``hdr``, ``eu``).
A SKU that does not match is an error, never a warning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bac_common.errors import BacError

__all__ = ["SKU_PATTERN", "Sku", "SkuError", "parse_sku", "validate_sku", "is_sku"]

SKU_PATTERN = re.compile(
    r"^bac-(?P<cat>[a-z0-9]+)-(?P<sub>[a-z0-9]+)-"
    r"(?P<name>[a-z0-9]+(?:[.-][a-z0-9]+)*)-"
    r"(?P<version>v\d+r\d+(?:\.\d+)?)"
    r"(?:-(?P<variant>[a-z0-9]+(?:-[a-z0-9]+)*))?$"
)


class SkuError(BacError):
    """A SKU outside the scheme. Exit code 1: it is data, found at run time."""


@dataclass(frozen=True, slots=True)
class Sku:
    cat: str
    sub: str
    name: str
    version: str
    variant: str | None = None

    def __str__(self) -> str:
        base = f"bac-{self.cat}-{self.sub}-{self.name}-{self.version}"
        return f"{base}-{self.variant}" if self.variant else base


def parse_sku(value: str) -> Sku:
    """Split a SKU into its fields or raise :class:`SkuError` with the reason."""
    text = value.strip()
    match = SKU_PATTERN.match(text)
    if match is None:
        raise SkuError(f"SKU does not follow the scheme: {text}", _reason(text))
    return Sku(match["cat"], match["sub"], match["name"], match["version"], match["variant"])


def validate_sku(value: str) -> str:
    """Return the SKU unchanged when it follows the scheme; raise otherwise."""
    return str(parse_sku(value))


def is_sku(value: str) -> bool:
    return SKU_PATTERN.match(value.strip()) is not None


def _reason(text: str) -> str:
    if text != text.lower():
        return "Every field is lowercase."
    if not text.startswith("bac-"):
        return "The prefix is `bac-`."
    if not re.search(r"-v\d+r\d+(?:\.\d+)?(?:-|$)", text):
        return "The version string `v<N>r<N>[.<N>]` is missing; expected bac-<cat>-<sub>-<name>-<version>[-<variant>]."
    if re.search(r"[^a-z0-9.-]", text):
        return "Only lowercase letters, digits, hyphens and dots inside the name are allowed."
    return "Expected bac-<cat>-<sub>-<name>-<version>[-<variant>] with at least four fields before the version."
