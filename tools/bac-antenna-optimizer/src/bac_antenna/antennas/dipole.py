# SPDX-License-Identifier: MIT
"""Half-wave strip dipole in free space – the smallest possible antenna type, used as the example for writing
your own and as the openEMS integration test (gain 2.15 dBi, resonance a little below half a wavelength).

[antenna]
type = "dipole"
[geometry]
strip_width_mm = 2.0
gap_mm = 1.0
[search]
length_mm = [100.0, 200.0]      # tip to tip
"""

from __future__ import annotations

from ..config import Config
from ..geometry import PRIORITY_METAL, FieldPlane, Model, Port, Primitive
from . import AntennaType, Params


class Dipole(AntennaType):
    name = "dipole"
    params = ("length_mm",)

    def validate_config(self, config: Config) -> list[str]:
        g = config.geometry
        return [] if "strip_width_mm" in g and "gap_mm" in g else ["dipole needs [geometry] strip_width_mm and gap_mm"]

    def valid(self, p: Params, config: Config) -> bool:
        return p["length_mm"] > 2 * float(config.geometry["gap_mm"])

    def model(self, p: Params, config: Config) -> Model:
        g = config.geometry
        w, gap, L = float(g["strip_width_mm"]), float(g["gap_mm"]), p["length_mm"]
        h = L / 2
        arms = [
            Primitive("box", "arm", "metal", PRIORITY_METAL, start=(gap / 2, -w / 2, 0.0), stop=(h, w / 2, 0.0)),
            Primitive("box", "arm", "metal", PRIORITY_METAL, start=(-h, -w / 2, 0.0), stop=(-gap / 2, w / 2, 0.0)),
        ]
        port = Port((-gap / 2, 0.0, 0.0), (gap / 2, 0.0, 0.0), "x", float(g.get("impedance_ohm", 73.0)))
        big = 1e9
        return Model(
            tuple(arms),
            (port,),
            {"x": (-h, -gap / 2, gap / 2, h), "y": (-w / 2, w / 2), "z": (0.0,)},
            notes=("half-wave strip dipole",),
            bounds=(-h, h, -w / 2, w / 2, 0.0, 0.0),
            edge_props=("arm",),
            field_planes=(FieldPlane("E_plane", (-big, -big, 0.0), (big, big, 0.0)),),
        )
