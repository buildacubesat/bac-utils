# SPDX-License-Identifier: MIT
from pathlib import Path

from bac_antenna.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def config(name: str = "cross_2200.toml", *overrides: str):
    return load_config(ROOT / "config" / name, list(overrides))


NOMINAL = dict(arm_x_mm=68.5, arm_y_mm=71.5, arm_width_mm=33.0, feed_offset_mm=12.0, pad_radius_mm=2.5)
