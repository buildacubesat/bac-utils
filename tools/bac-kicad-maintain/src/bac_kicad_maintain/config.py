# SPDX-License-Identifier: MIT
"""Settings: the sizes the operations enforce and which ones run by default.

Defaults are the Build a CubeSat board conventions, so the tool works
without a config file. ``init`` writes them to
``~/.config/bac/bac-kicad-maintain.toml`` for another project to change;
``--config PATH`` names another file for one run.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from bac_common.config import load_toml
from bac_common.errors import ConfigError

TOOL = "bac-kicad-maintain"
OPERATIONS = ("text", "courtyards", "vias", "labels")
VIA_TYPES = ("through", "blind", "micro")

__all__ = ["TOOL", "OPERATIONS", "VIA_TYPES", "Settings", "CONFIG_TEMPLATE", "load_settings", "number"]


@dataclass(frozen=True, slots=True)
class Settings:
    text: bool = True
    text_width: float = 0.8
    text_height: float = 0.8
    text_thickness: float = 0.1
    text_center: bool = True
    text_keep_upright: bool = True
    text_layers: tuple[str, ...] = ()
    courtyards: bool = True
    courtyard_width: float = 0.05
    vias: bool = False
    via_diameter: float = 0.5
    via_drill: float = 0.2
    preserve_nets: tuple[str, ...] = ("GND",)
    via_types: tuple[str, ...] = ("through",)
    labels: bool = False
    label_size_mil: float = 50
    exclude: tuple[str, ...] = ()

    def enabled(self) -> set[str]:
        """The operations the config turns on; the command line can select others."""
        return {name for name in OPERATIONS if getattr(self, name)}

    @property
    def label_size_mm(self) -> Decimal:
        return number(self.label_size_mil) * Decimal("0.0254")


DEFAULTS = Settings()

CONFIG_TEMPLATE = f"""# {TOOL}.toml
# Build a CubeSat – {TOOL} configuration. Every value is optional;
# these are the BAC board conventions. `enabled` says which operations
# `check` and `apply` run when no operation flag is given; a flag on the
# command line selects only the flagged operations.

[text]
enabled = {str(DEFAULTS.text).lower()}
width = {DEFAULTS.text_width}
height = {DEFAULTS.text_height}
thickness = {DEFAULTS.text_thickness}
center = {str(DEFAULTS.text_center).lower()}
keep_upright = {str(DEFAULTS.text_keep_upright).lower()}
# Empty means every board and footprint text layer, reference and value
# fields included. Silkscreen only: layers = ["F.SilkS", "B.SilkS"]
layers = []

[courtyards]
enabled = {str(DEFAULTS.courtyards).lower()}
width = {DEFAULTS.courtyard_width}

[vias]
enabled = {str(DEFAULTS.vias).lower()}
diameter = {DEFAULTS.via_diameter}
drill = {DEFAULTS.via_drill}
# Case-sensitive glob patterns matched against the whole net name; vias on
# these nets keep their size. Add "*/GND" for hierarchical grounds.
preserve_nets = [{", ".join(f'"{n}"' for n in DEFAULTS.preserve_nets)}]
# Which via types are resized: through, blind, micro.
types = [{", ".join(f'"{t}"' for t in DEFAULTS.via_types)}]

[labels]
enabled = {str(DEFAULTS.labels).lower()}
# Local, global and hierarchical schematic labels only.
size_mil = {DEFAULTS.label_size_mil:g}

[files]
# Glob patterns matched against each file's path relative to the directory
# given, or against its name. Example: exclude = ["vendor/*", "generated/*"]
exclude = []
"""


def number(value: object) -> Decimal:
    """``value`` as a Decimal; a non-number or a non-finite one is a :class:`ConfigError`."""
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        raise ConfigError(f"Not a number: {value!r}")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ConfigError(f"Not a number: {value!r}") from exc
    if not result.is_finite():
        raise ConfigError(f"Not a finite number: {value!r}")
    return result


def load_settings(config_path: str | None) -> Settings:
    """The config file merged over the defaults; a missing default file means defaults."""
    data = load_toml(TOOL, config_path)
    known = {"text", "courtyards", "vias", "labels", "files"}
    for section in data:
        if section not in known:
            raise ConfigError(f"Unknown config section [{section}].", "Known: " + ", ".join(sorted(known)) + ".")
    text, courtyards = _table(data, "text"), _table(data, "courtyards")
    vias, labels, files = _table(data, "vias"), _table(data, "labels"), _table(data, "files")
    _known_keys(text, "text", ("enabled", "width", "height", "thickness", "center", "keep_upright", "layers"))
    _known_keys(courtyards, "courtyards", ("enabled", "width"))
    _known_keys(vias, "vias", ("enabled", "diameter", "drill", "preserve_nets", "types"))
    _known_keys(labels, "labels", ("enabled", "size_mil"))
    _known_keys(files, "files", ("exclude",))
    settings = Settings(
        text=_flag(text, "enabled", DEFAULTS.text),
        text_width=_size(text, "width", DEFAULTS.text_width),
        text_height=_size(text, "height", DEFAULTS.text_height),
        text_thickness=_size(text, "thickness", DEFAULTS.text_thickness),
        text_center=_flag(text, "center", DEFAULTS.text_center),
        text_keep_upright=_flag(text, "keep_upright", DEFAULTS.text_keep_upright),
        text_layers=_strings(text, "layers", DEFAULTS.text_layers),
        courtyards=_flag(courtyards, "enabled", DEFAULTS.courtyards),
        courtyard_width=_size(courtyards, "width", DEFAULTS.courtyard_width),
        vias=_flag(vias, "enabled", DEFAULTS.vias),
        via_diameter=_size(vias, "diameter", DEFAULTS.via_diameter),
        via_drill=_size(vias, "drill", DEFAULTS.via_drill),
        preserve_nets=_strings(vias, "preserve_nets", DEFAULTS.preserve_nets),
        via_types=_strings(vias, "types", DEFAULTS.via_types),
        labels=_flag(labels, "enabled", DEFAULTS.labels),
        label_size_mil=_size(labels, "size_mil", DEFAULTS.label_size_mil),
        exclude=_strings(files, "exclude", DEFAULTS.exclude),
    )
    validate(settings)
    return settings


def validate(settings: Settings) -> None:
    """The checks that hold for the config and for command-line overrides alike."""
    unknown = sorted(set(settings.via_types) - set(VIA_TYPES))
    if unknown:
        raise ConfigError("Unknown via type: " + ", ".join(unknown) + ".", "Allowed: " + ", ".join(VIA_TYPES) + ".")
    if not settings.via_types:
        raise ConfigError("vias.types must name at least one via type.")
    if number(settings.via_drill) >= number(settings.via_diameter):
        raise ConfigError(
            f"The via drill ({settings.via_drill} mm) must be smaller than its diameter ({settings.via_diameter} mm)."
        )
    size = settings.label_size_mm
    if size != size.quantize(Decimal("0.000001")):
        raise ConfigError(f"A label size of {settings.label_size_mil} mil needs more than six decimals in mm.")


def _table(data: dict, key: str) -> dict:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table.")
    return value


def _known_keys(table: dict, section: str, keys: tuple[str, ...]) -> None:
    for key in table:
        if key not in keys:
            raise ConfigError(f"Unknown key {section}.{key}.", f"Known: {', '.join(keys)}.")


def _flag(table: dict, key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false, got {value!r}.")
    return value


def _size(table: dict, key: str, default: float) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{key} must be a number, got {value!r}.")
    n = number(value)
    if n <= 0 or n.as_tuple().exponent < -6:
        raise ConfigError(f"{key} must be positive with at most six decimals, got {value!r}.")
    return float(value)


def _strings(table: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = table.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key} must be a list of strings.")
    return tuple(value)
