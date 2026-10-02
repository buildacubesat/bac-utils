# SPDX-License-Identifier: MIT
"""Polarization helpers. Convention: IEEE, e^{jwt}, wave travelling along +z (broadside)."""

from __future__ import annotations

import math


def axial_ratio_db(ex: complex, ey: complex) -> float:
    s0 = abs(ex) ** 2 + abs(ey) ** 2
    s1 = abs(ex) ** 2 - abs(ey) ** 2
    s2 = 2 * (ex * ey.conjugate()).real
    linear = math.sqrt(max(0.0, s1 * s1 + s2 * s2))
    minor2 = max(0.0, (s0 - linear) / 2)
    if minor2 <= 1e-30 * max(s0, 1e-300):
        return 99.0
    return min(99.0, 20 * math.log10(math.sqrt(max(0.0, (s0 + linear) / 2) / minor2)))


def circular_components(ex: complex, ey: complex) -> tuple[complex, complex]:
    """(E_rhcp, E_lhcp) for a +z travelling wave; RHCP unit vector (x - jy)/sqrt2."""
    return (ex + 1j * ey) / math.sqrt(2), (ex - 1j * ey) / math.sqrt(2)


def rotation_sense(ex: complex, ey: complex) -> int:
    """+1 RHCP, -1 LHCP, 0 linear (IEEE, +z)."""
    er, el = circular_components(ex, ey)
    if abs(abs(er) - abs(el)) < 1e-12 * (abs(er) + abs(el) + 1e-300):
        return 0
    return 1 if abs(er) > abs(el) else -1


def hybrid_weights(phase_deg: float = 90.0, amplitude_db: float = 0.0) -> list:
    """Incident-wave weights for a two-feed 90 deg hybrid, both orientations.

    Port B lags port A by `phase_deg`; `amplitude_db` is B relative to A. Ideal: 90, 0.
    Normalised to unit incident power.
    """
    import cmath

    import numpy as np

    r = 10 ** (amplitude_db / 20)
    out = []
    for sign in (-1, 1):
        a = np.array([1.0, r * cmath.exp(1j * sign * math.radians(phase_deg))])
        out.append(a / np.linalg.norm(a))
    return out
