# SPDX-License-Identifier: MIT
"""Deployable UHF turnstile on the end face of a CubeSat body: four tape elements lying in the plane of the face
(deployment angle 0 deg), each fed against the body at its root. Ports are +x, +y, -x, -y; the `turnstile` feed
network drives them 0 / -90 / -180 / -270 deg for circular polarization along the face normal.

[antenna]
type = "turnstile"
[geometry]
body_x_mm = 100.0          # body cross-section
body_y_mm = 100.0
body_z_mm = 340.0          # body length; the face is at z = 0, the body below it
tape_width_mm = 3.0
tape_thickness_mm = 0.1
element_height_mm = 3.0    # tape above the face
root_inset_mm = 5.0        # feed point inside the face edge
[search]
element_length_mm = [140.0, 200.0]   # from the feed point to the tip

Angled elements and a stowed configuration are not modelled yet.
"""

from __future__ import annotations

from ..config import Config
from ..geometry import PRIORITY_METAL, FieldPlane, Model, Port, Primitive
from . import AntennaType, Params


class Turnstile(AntennaType):
    name = "turnstile"
    params = ("element_length_mm",)

    def validate_config(self, config: Config) -> list[str]:
        need = (
            "body_x_mm",
            "body_y_mm",
            "body_z_mm",
            "tape_width_mm",
            "tape_thickness_mm",
            "element_height_mm",
            "root_inset_mm",
        )
        missing = [k for k in need if k not in config.geometry]
        return [f"turnstile needs [geometry] {', '.join(missing)}"] if missing else []

    def valid(self, p: Params, config: Config) -> bool:
        g = config.geometry
        return (
            p["element_length_mm"] > 0
            and float(g["root_inset_mm"]) < min(float(g["body_x_mm"]), float(g["body_y_mm"])) / 2
        )

    def model(self, p: Params, config: Config) -> Model:
        g = config.geometry
        bx, by, bz = float(g["body_x_mm"]) / 2, float(g["body_y_mm"]) / 2, float(g["body_z_mm"])
        w, t, h, inset, L = (
            float(g["tape_width_mm"]),
            float(g["tape_thickness_mm"]),
            float(g["element_height_mm"]),
            float(g["root_inset_mm"]),
            p["element_length_mm"],
        )
        z0 = float(g.get("impedance_ohm", 50.0))
        prims = [Primitive("box", "body", "metal", PRIORITY_METAL, start=(-bx, -by, -bz), stop=(bx, by, 0.0))]
        ports = []
        xs, ys = {-bx, bx}, {-by, by}
        for dx, dy, half in ((1, 0, bx), (0, 1, by), (-1, 0, bx), (0, -1, by)):
            r0 = half - inset  # feed point along the element's axis
            r1 = r0 + L
            if dx:
                start, stop = (min(dx * r0, dx * r1), -w / 2, h - t / 2), (max(dx * r0, dx * r1), w / 2, h + t / 2)
                xs |= {dx * r0, dx * r1}
                ys |= {-w / 2, w / 2}
                port = Port((dx * r0, 0.0, 0.0), (dx * r0, 0.0, h - t / 2), "z", z0)
            else:
                start, stop = (-w / 2, min(dy * r0, dy * r1), h - t / 2), (w / 2, max(dy * r0, dy * r1), h + t / 2)
                ys |= {dy * r0, dy * r1}
                xs |= {-w / 2, w / 2}
                port = Port((0.0, dy * r0, 0.0), (0.0, dy * r0, h - t / 2), "z", z0)
            prims.append(Primitive("box", "element", "metal", PRIORITY_METAL, start=start, stop=stop))
            ports.append(port)
        reach = max(bx, by) - inset + L
        big = 1e9
        return Model(
            tuple(prims),
            tuple(ports),
            {"x": tuple(sorted(xs)), "y": tuple(sorted(ys)), "z": (-bz, 0.0, h - t / 2, h + t / 2)},
            notes=("turnstile, four tape elements in the face plane",),
            bounds=(-reach, reach, -reach, reach, -bz, h + t / 2),
            phase_centre=(0.0, 0.0, 0.0),
            edge_props=("element",),
            field_planes=(
                FieldPlane("E_face", (-big, -big, h), (big, big, h)),
                FieldPlane("E_xz", (-big, 0.0, -big), (big, 0.0, big)),
            ),
        )
