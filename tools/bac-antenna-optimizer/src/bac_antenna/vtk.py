from __future__ import annotations

import math
from pathlib import Path

from .geometry import Model


def write_geometry_vtp(path: Path, model: Model, segments: int = 64) -> None:
    """ParaView preview of the metal parts of the Model the solver receives: planar copper as faces,
    cylinders as walls, ports as small markers. Dimensional check only – not the CSXCAD discretisation."""
    points: list[tuple[float, float, float]] = []
    polys: list[tuple[int, ...]] = []
    for p in model.primitives:
        if p.material != "metal":
            continue
        if p.kind == "polygon":
            base = len(points)
            points.extend((x, y, p.elevation) for x, y in p.points)
            polys.append(tuple(range(base, base + len(p.points))))
        elif p.kind == "box":
            (x0, y0, z0), (x1, y1, z1) = p.start, p.stop
            base = len(points)
            points.extend([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)])
            polys.append((base, base + 1, base + 2, base + 3))
        elif p.kind == "cylinder":
            base = len(points)
            for z in (p.start[2], p.stop[2]):
                for i in range(segments):
                    a = 2 * math.pi * i / segments
                    points.append((p.radius * math.cos(a), p.radius * math.sin(a), z))
            for i in range(segments):
                n = (i + 1) % segments
                polys.append((base + i, base + n, base + segments + n, base + segments + i))
    for port in model.ports:
        (x, y, z0), (_, _, z1) = port.start, port.stop
        base = len(points)
        points.extend([(x - 0.4, y, z0), (x + 0.4, y, z0), (x + 0.4, y, z1), (x - 0.4, y, z1)])
        polys.append((base, base + 1, base + 2, base + 3))

    connectivity = " ".join(str(v) for poly in polys for v in poly)
    offsets, total = [], 0
    for poly in polys:
        total += len(poly)
        offsets.append(str(total))
    coordinates = " ".join(f"{x:.6g} {y:.6g} {z:.6g}" for x, y, z in points)
    path.write_text(f'''<?xml version="1.0"?>
<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">
  <PolyData><Piece NumberOfPoints="{len(points)}" NumberOfPolys="{len(polys)}">
    <Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">{coordinates}</DataArray></Points>
    <Polys>
      <DataArray type="Int32" Name="connectivity" format="ascii">{connectivity}</DataArray>
      <DataArray type="Int32" Name="offsets" format="ascii">{" ".join(offsets)}</DataArray>
    </Polys>
  </Piece></PolyData>
</VTKFile>
''')
