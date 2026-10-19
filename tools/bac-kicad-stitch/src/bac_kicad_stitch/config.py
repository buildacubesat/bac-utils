# SPDX-License-Identifier: MIT
"""Settings: via geometry, the clearances a candidate must keep, and how dense the stitching is.

Defaults are the Build a CubeSat board conventions, so the tool works
without a config file. ``init`` writes them to
``~/.config/bac/bac-kicad-stitch.toml``; ``--config PATH`` names another
file for one run, and the command-line flags override single values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from bac_common.config import load_toml
from bac_common.errors import ConfigError

TOOL = "bac-kicad-stitch"
GROUP_NAME = "bac-stitch"
C_MM_PER_S = 299_792_458_000.0
COURTYARD_MODES = ("allow", "avoid", "avoid-fine-pitch")

__all__ = [
    "TOOL",
    "GROUP_NAME",
    "COURTYARD_MODES",
    "Settings",
    "CONFIG_TEMPLATE",
    "load_settings",
    "validate",
    "pitch_from_frequency",
]


@dataclass(frozen=True, slots=True)
class Settings:
    net: str = "GND"
    via_size: float = 0.6
    via_drill: float = 0.3
    clearance: float = 0.2
    hole_to_hole: float = 0.25
    edge_clearance: float = 0.5
    margin: float = 0.05
    max_frequency_hz: float | None = None
    pitch: float | None = 10.0
    fraction: float = 20.0
    epsilon_r: float | None = None
    min_layers: int = 2
    keep_zones: bool = False
    courtyards: str = "avoid-fine-pitch"
    fine_pitch: float = 0.65
    fine_pitch_pads: int = 6
    edge_fence: bool = False
    edge_fence_pitch: float | None = None
    step: float = 0.1

    @property
    def via_radius(self) -> float:
        return self.via_size / 2

    def effective_pitch(self, board_epsilon_r: float | None) -> float:
        """The stitching pitch: ``pitch`` when set, else λ/fraction at ``max_frequency_hz``."""
        if self.max_frequency_hz is not None:
            er = self.epsilon_r if self.epsilon_r is not None else (board_epsilon_r or 4.4)
            return pitch_from_frequency(self.max_frequency_hz, er, self.fraction)
        if self.pitch is None:
            raise ConfigError("Neither a pitch nor a maximum frequency is set.")
        return self.pitch

    def fence_pitch(self, pitch: float) -> float:
        return self.edge_fence_pitch if self.edge_fence_pitch is not None else pitch / 2


def pitch_from_frequency(frequency_hz: float, epsilon_r: float, fraction: float) -> float:
    """λ/fraction in the dielectric: the wavelength at ``frequency_hz`` divided by ``fraction``."""
    wavelength = C_MM_PER_S / (frequency_hz * math.sqrt(epsilon_r))
    return wavelength / fraction


DEFAULTS = Settings()

CONFIG_TEMPLATE = f"""# {TOOL}.toml
# Build a CubeSat – {TOOL} configuration. Every value is optional; these
# are the BAC board conventions. A command-line flag overrides its value
# for one run.

[via]
net = "{DEFAULTS.net}"
size = {DEFAULTS.via_size}
drill = {DEFAULTS.via_drill}

[rules]
# Copper clearance to other nets, hole-to-hole clearance, and the copper
# to board-edge clearance, as in the project's design rules.
clearance = {DEFAULTS.clearance}
hole_to_hole = {DEFAULTS.hole_to_hole}
edge_clearance = {DEFAULTS.edge_clearance}
# Extra distance kept beyond every clearance so a via never sits exactly on
# a DRC limit.
margin = {DEFAULTS.margin}

[placement]
# The target pitch in mm: every point of the ground copper ends up within
# this distance of a ground via. Set max_frequency_hz instead to derive it
# as wavelength / fraction in the board's dielectric (epsilon_r from the
# stackup unless set here).
pitch = {DEFAULTS.pitch}
# max_frequency_hz = 1e9
fraction = {DEFAULTS.fraction:g}
# epsilon_r = 4.4
# A via must sit in the ground fill of at least this many copper layers.
min_layers = {DEFAULTS.min_layers}
# Other nets' zone fills refill around a new via, so they are no obstacle
# unless keep_zones is true (then planes are not perforated).
keep_zones = {str(DEFAULTS.keep_zones).lower()}
# Courtyards: "allow", "avoid", or "avoid-fine-pitch" – stay out of the
# courtyards of footprints with at least fine_pitch_pads pads whose pad
# pitch is below fine_pitch mm.
courtyards = "{DEFAULTS.courtyards}"
fine_pitch = {DEFAULTS.fine_pitch}
fine_pitch_pads = {DEFAULTS.fine_pitch_pads}
# A row of vias along the board edge, at edge_fence_pitch (default: half
# the pitch).
edge_fence = {str(DEFAULTS.edge_fence).lower()}
# edge_fence_pitch = 2.5
# Candidate grid step in mm. Finer finds more spots under tight copper and
# takes longer.
step = {DEFAULTS.step}
"""

_SECTIONS = {
    "via": {"net": "net", "size": "via_size", "drill": "via_drill"},
    "rules": {
        "clearance": "clearance",
        "hole_to_hole": "hole_to_hole",
        "edge_clearance": "edge_clearance",
        "margin": "margin",
    },
    "placement": {
        "pitch": "pitch",
        "max_frequency_hz": "max_frequency_hz",
        "fraction": "fraction",
        "epsilon_r": "epsilon_r",
        "min_layers": "min_layers",
        "keep_zones": "keep_zones",
        "courtyards": "courtyards",
        "fine_pitch": "fine_pitch",
        "fine_pitch_pads": "fine_pitch_pads",
        "edge_fence": "edge_fence",
        "edge_fence_pitch": "edge_fence_pitch",
        "step": "step",
    },
}


def load_settings(config_path: str | None) -> Settings:
    """The config file merged over the defaults; a missing default file means defaults."""
    data = load_toml(TOOL, config_path)
    for section in data:
        if section not in _SECTIONS:
            raise ConfigError(f"Unknown config section [{section}].", "Known: " + ", ".join(_SECTIONS) + ".")
    overrides: dict[str, object] = {}
    for section, keys in _SECTIONS.items():
        table = data.get(section, {})
        if not isinstance(table, dict):
            raise ConfigError(f"[{section}] must be a table.")
        for key, value in table.items():
            if key not in keys:
                raise ConfigError(f"Unknown key {key!r} in [{section}].", "Known: " + ", ".join(keys) + ".")
            overrides[keys[key]] = value
    if "max_frequency_hz" in overrides and "pitch" not in overrides:
        overrides["pitch"] = None
    settings = replace(DEFAULTS, **overrides)
    validate(settings)
    return settings


def validate(s: Settings) -> None:
    for name in ("via_size", "via_drill", "clearance", "hole_to_hole", "edge_clearance", "step", "fine_pitch"):
        value = getattr(s, name)
        if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
            raise ConfigError(f"{name} must be a positive number, got {value!r}.")
    if isinstance(s.margin, bool) or not isinstance(s.margin, int | float) or s.margin < 0:
        raise ConfigError(f"margin must be zero or positive, got {s.margin!r}.")
    if s.via_drill >= s.via_size:
        raise ConfigError(f"The via drill ({s.via_drill}) must be smaller than the via size ({s.via_size}).")
    for name in ("pitch", "max_frequency_hz", "epsilon_r", "edge_fence_pitch"):
        value = getattr(s, name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int | float) or value <= 0):
            raise ConfigError(f"{name} must be a positive number, got {value!r}.")
    if s.pitch is None and s.max_frequency_hz is None:
        raise ConfigError("Set a pitch or a maximum frequency.")
    if isinstance(s.fraction, bool) or not isinstance(s.fraction, int | float) or s.fraction <= 0:
        raise ConfigError(f"fraction must be a positive number, got {s.fraction!r}.")
    if isinstance(s.min_layers, bool) or not isinstance(s.min_layers, int) or s.min_layers < 1:
        raise ConfigError(f"min_layers must be a positive integer, got {s.min_layers!r}.")
    if isinstance(s.fine_pitch_pads, bool) or not isinstance(s.fine_pitch_pads, int) or s.fine_pitch_pads < 2:
        raise ConfigError(f"fine_pitch_pads must be an integer of at least 2, got {s.fine_pitch_pads!r}.")
    if s.courtyards not in COURTYARD_MODES:
        raise ConfigError(f"courtyards must be one of {', '.join(COURTYARD_MODES)}, got {s.courtyards!r}.")
    for name in ("edge_fence", "keep_zones"):
        if not isinstance(getattr(s, name), bool):
            raise ConfigError(f"{name} must be true or false, got {getattr(s, name)!r}.")
    if not isinstance(s.net, str) or not s.net:
        raise ConfigError("net must be a non-empty string.")
