"""Feed networks: how the ports are driven together.

The solver runs each port alone; the network is applied afterwards as a vector of incident-wave weights. The
backend evaluates every option the network offers and keeps the one with the most co-polar gain at band centre
(the two hands of a quadrature network, say), so a wrong guess about which port leads costs nothing.

[feed_network]
mode = "single" | "quadrature" | "turnstile" | "custom"   # default from the port count: 1, 2, 4
phase_error_deg = 0.0       # deviation of the quadrature phase from 90 deg (a real hybrid's error)
amplitude_error_db = 0.0    # port 2 relative to port 1
weights = [[re, im], ...]   # custom only; one entry per port, any scale

Legacy `[polarization] hybrid_phase_deg / hybrid_amplitude_db` are mapped to phase_error_deg / amplitude_error_db.
"""
from __future__ import annotations

import cmath
import math

import numpy as np

from .config import Config


def default_mode(n_ports: int) -> str:
    return {1: "single", 2: "quadrature", 4: "turnstile"}.get(n_ports, "custom")


def weight_options(config: Config, n_ports: int) -> list[np.ndarray]:
    fn = config.feed_network
    mode = str(fn.get("mode", default_mode(n_ports)))
    phase = 90.0 + float(fn.get("phase_error_deg", 0.0))
    r = 10 ** (float(fn.get("amplitude_error_db", 0.0)) / 20)
    if mode == "single":
        if n_ports != 1:
            raise ValueError(f"feed_network single needs 1 port, model has {n_ports}")
        return [np.array([1.0 + 0j])]
    if mode == "quadrature":
        if n_ports != 2:
            raise ValueError(f"feed_network quadrature needs 2 ports, model has {n_ports}")
        out = []
        for sign in (-1, 1):
            a = np.array([1.0, r * cmath.exp(1j * sign * math.radians(phase))])
            out.append(a / np.linalg.norm(a))
        return out
    if mode == "turnstile":
        if n_ports != 4:
            raise ValueError(f"feed_network turnstile needs 4 ports (+x, +y, -x, -y), model has {n_ports}")
        out = []
        for sign in (-1, 1):
            # crossed dipoles: opposite elements in anti-phase, the two dipoles in quadrature
            a = np.array([1.0, r * cmath.exp(1j * sign * math.radians(phase)), -1.0, -r * cmath.exp(1j * sign * math.radians(phase))])
            out.append(a / np.linalg.norm(a))
        return out
    if mode == "custom":
        w = fn.get("weights")
        if not w or len(w) != n_ports:
            raise ValueError(f"feed_network custom needs `weights` with {n_ports} [re, im] entries")
        a = np.array([complex(float(x[0]), float(x[1])) for x in w])
        return [a / np.linalg.norm(a)]
    raise ValueError(f"unknown feed_network mode {mode!r}")


def describe(config: Config, n_ports: int) -> str:
    return str(config.feed_network.get("mode", default_mode(n_ports)))
