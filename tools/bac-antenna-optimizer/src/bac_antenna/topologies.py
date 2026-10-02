# SPDX-License-Identifier: MIT
"""Legacy names; antenna types live in bac_antenna.antennas (patch types in bac_antenna.antennas.patch)."""

from .antennas import get_antenna as get_topology  # noqa: F401
from .antennas.patch import AnnularRing, CrossPatch, chamfered_square  # noqa: F401
