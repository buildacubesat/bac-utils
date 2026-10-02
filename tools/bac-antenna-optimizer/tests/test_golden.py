"""The 0.6 antenna-type refactor must build exactly the model and mesh lines 0.5.4 built for the frozen designs.
tests/golden/*.json were captured with 0.5.4 (primitives, ports, fixed lines and the pre-smoothing mesh lines)."""
import json
from pathlib import Path
import unittest

import numpy as np

from bac_antenna.antennas import get_antenna
from bac_antenna.config import load_config
from bac_antenna.core import full_params
from bac_antenna.openems_backend import build_lines
from helpers import ROOT

GOLDEN = Path(__file__).parent / "golden"


class GoldenModelTests(unittest.TestCase):
    def _check(self, cfg_name: str, golden_name: str):
        config = load_config(ROOT / "config" / f"{cfg_name}.toml")
        params = full_params(json.loads((ROOT / "designs" / f"{cfg_name}.json").read_text()), config)
        model = get_antenna(config).model(params, config)
        golden = json.loads((GOLDEN / f"{golden_name}.json").read_text())
        self.assertEqual(len(model.primitives), len(golden["primitives"]))
        for prim, g in zip(model.primitives, golden["primitives"]):
            for key, val in g.items():
                mine = getattr(prim, key)
                if key == "points":
                    self.assertEqual([list(q) for q in mine], val, f"{prim.prop}.{key}")
                elif isinstance(val, list):
                    self.assertEqual(list(mine), val, f"{prim.prop}.{key}")
                else:
                    self.assertEqual(mine, val, f"{prim.prop}.{key}")
        self.assertEqual(len(model.ports), len(golden["ports"]))
        for port, g in zip(model.ports, golden["ports"]):
            self.assertEqual([list(port.start), list(port.stop), port.direction, port.impedance_ohm], [g["start"], g["stop"], g["direction"], g["impedance_ohm"]])
        self.assertEqual({k: list(v) for k, v in model.fixed_lines.items()}, golden["fixed_lines"])
        self.assertEqual(list(model.refine), golden["refine"])
        self.assertEqual(model.phase_centre[2], golden["z_patch"])
        m = config.mesh
        margin = float(m["air_margin_mm"])
        xmin, xmax, ymin, ymax, zmin, zmax = model.extent()
        self.assertAlmostEqual(xmax + margin, golden["half"])
        dom = {"x": (xmin - margin, xmax + margin), "y": (ymin - margin, ymax + margin), "z": (zmin - margin, zmax + margin)}
        lines = build_lines(model, m, dom)
        for ax in "xyz":
            np.testing.assert_allclose(lines[ax], golden["lines"][ax], rtol=0, atol=1e-12, err_msg=ax)

    def test_frozen_2200(self):
        self._check("cross_2200_dual_v2", "frozen_2200")

    def test_frozen_2400(self):
        self._check("cross_2400_dual_v2", "frozen_2400")


if __name__ == "__main__":
    unittest.main()
