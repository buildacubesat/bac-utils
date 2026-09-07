# SPDX-License-Identifier: MIT
"""Settings: the sizes and prefixes the lint enforces, and where the rules live.

Defaults are the Build a CubeSat library conventions, so the tool works
without a config file. ``init`` writes them to
``~/.config/bac/bac-kicad-symfields.toml`` for another library to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bac_common.config import expand, load_toml
from bac_common.errors import ConfigError

TOOL = "bac-kicad-symfields"

__all__ = ["TOOL", "Settings", "CONFIG_TEMPLATE", "load_settings"]


@dataclass(frozen=True, slots=True)
class Settings:
    rules_dir: Path | None = None
    property_sizes: tuple[float, ...] = (1.27, 0.762)
    property_fix_size: float = 0.762
    pin_size: float = 1.27
    footprint_prefix: str = "bac KiCad Library Footprints v1:"
    fp_font_size: float = 0.8
    fp_font_thickness: float = 0.1
    tolerance: float = 0.001

    def property_size_ok(self, size: float) -> bool:
        return any(abs(size - allowed) <= self.tolerance for allowed in self.property_sizes)

    def close(self, a: float, b: float) -> bool:
        return abs(a - b) <= self.tolerance


DEFAULTS = Settings()

CONFIG_TEMPLATE = f"""# {TOOL}.toml
# Build a CubeSat – {TOOL} configuration. Every value is optional; these are
# the BAC library conventions. `rules` is the directory of TOML field rules
# used when --rules is not given.
rules = ""
tolerance = {DEFAULTS.tolerance}

[symbol]
# Font sizes (mm) a property may have; anything else is a lint finding and
# `fix` sets it to property_fix_size. Pin names, pin numbers and text items
# must use pin_size.
property_sizes = [{", ".join(str(s) for s in DEFAULTS.property_sizes)}]
property_fix_size = {DEFAULTS.property_fix_size}
pin_size = {DEFAULTS.pin_size}
# Every Footprint property must start with this library nickname and colon.
footprint_prefix = "{DEFAULTS.footprint_prefix}"

[footprint]
# Reference, Value and text items in footprints use this font.
font_size = {DEFAULTS.fp_font_size}
font_thickness = {DEFAULTS.fp_font_thickness}
"""


def load_settings(config_path: str | None) -> Settings:
    """The config file merged over the defaults; a missing default file means defaults."""
    data = load_toml(TOOL, config_path)
    symbol = _table(data, "symbol")
    footprint = _table(data, "footprint")
    rules = data.get("rules") or None
    sizes = symbol.get("property_sizes", DEFAULTS.property_sizes)
    if not isinstance(sizes, list | tuple) or not sizes or not all(isinstance(s, int | float) for s in sizes):
        raise ConfigError("[symbol] property_sizes must be a non-empty list of numbers.")
    return Settings(
        rules_dir=expand(str(rules)) if rules else None,
        property_sizes=tuple(float(s) for s in sizes),
        property_fix_size=_number(symbol, "property_fix_size", DEFAULTS.property_fix_size),
        pin_size=_number(symbol, "pin_size", DEFAULTS.pin_size),
        footprint_prefix=str(symbol.get("footprint_prefix", DEFAULTS.footprint_prefix)),
        fp_font_size=_number(footprint, "font_size", DEFAULTS.fp_font_size),
        fp_font_thickness=_number(footprint, "font_thickness", DEFAULTS.fp_font_thickness),
        tolerance=_number(data, "tolerance", DEFAULTS.tolerance),
    )


def _table(data: dict, key: str) -> dict:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table.")
    return value


def _number(table: dict, key: str, default: float) -> float:
    value = table.get(key, default)
    if not isinstance(value, int | float) or value <= 0:
        raise ConfigError(f"{key} must be a positive number, got {value!r}.")
    return float(value)
