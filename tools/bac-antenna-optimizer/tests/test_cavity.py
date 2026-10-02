import math
import unittest

import numpy as np

from bac_antenna.cavity import Cavity, CavityBackend, bore_isolation_db_per_mm, eigenmodes, rasterise, ring_root
from bac_antenna.geometry import Shape, ring_outline
from bac_antenna.topologies import CrossPatch
from helpers import NOMINAL, config


def rect(L, W):
    return ((-L / 2, 0), (-L / 2, -W / 2), (L / 2, -W / 2), (L / 2, W / 2), (-L / 2, W / 2))


class SolverTests(unittest.TestCase):
    def test_rectangle_is_exact(self):
        m = eigenmodes(rasterise(Shape(rect(57, 36), 0, 0, ((10, 0),), 36), 0.5, 0.0), 4)
        self.assertAlmostEqual(math.sqrt(m.lam[1]) * 1e-3, math.pi / 57, delta=1e-4)

    def test_open_and_shorted_ring_match_bessel(self):
        a, b = 6.6, 16.7
        for shorted in (False, True):
            m = eigenmodes(rasterise(Shape(ring_outline(b, 0, 3), 0 if shorted else a, a if shorted else 0, ((12, 0),), b - a),
                                     0.25, 0.0), 6)
            ks = np.sqrt(m.lam) * 1e-3
            exact = ring_root(a / b, shorted) / b
            self.assertLess(np.min(np.abs(ks - exact)) / exact, 0.012)

    def test_shorted_ring_has_monopolar_mode_below_tm11(self):
        a, b = 6.6, 16.7
        m = eigenmodes(rasterise(Shape(ring_outline(b, 0, 3), 0, a, ((12, 0),), b - a), 0.25, 0.0), 4)
        tm01 = ring_root(a / b, True, n=0) / b
        self.assertAlmostEqual(math.sqrt(m.lam[0]) * 1e-3, tm01, delta=0.012 * tm01)

    def test_bore_isolation(self):
        self.assertAlmostEqual(bore_isolation_db_per_mm(10.0, 2.245e9), 3.17, delta=0.03)


class CrossPatchTests(unittest.TestCase):
    def cavity(self, *overrides, **p):
        c = config("cross_2200.toml", *overrides)
        return Cavity.build(CrossPatch().shape(dict(NOMINAL, **p), c), c).with_pad(NOMINAL["pad_radius_mm"], c), c

    def test_short_adds_mode_without_broadside(self):
        cav, _ = self.cavity("outline.bore_short=true")
        table = cav.mode_table(47.0)
        first = next(m for m in table if m["f_hz"] > 1e6)
        self.assertIn("no broadside", first["kind"])
        self.assertLess(first["f_hz"], 1.9e9)
        cav, _ = self.cavity("outline.bore_short=false")
        first = next(m for m in cav.mode_table(47.0) if m["f_hz"] > 1e6)
        self.assertIn("broadside", first["kind"])

    def test_arm_swap_flips_hand(self):
        c = config()
        d = dict(arm_x_mm=57.92, arm_y_mm=63.92, arm_width_mm=37.0, feed_offset_mm=13.97, pad_radius_mm=2.51)  # CP design at 2.245 GHz
        a = CavityBackend().evaluate(d, c, None).bands["tx"].hand
        b = CavityBackend().evaluate(dict(d, arm_x_mm=d["arm_y_mm"], arm_y_mm=d["arm_x_mm"]), c, None).bands["tx"].hand
        self.assertEqual({a, b}, {"rhcp", "lhcp"})

    def test_dual_feed_gives_wideband_cp(self):
        c = config("cross_2200.toml", 'feed.mode="dual"')
        p = dict(arm_x_mm=70.4, arm_y_mm=70.4, arm_width_mm=33.8, feed_offset_mm=12.3, pad_radius_mm=2.3)
        m = CavityBackend().evaluate(p, c, None).bands["tx"]
        self.assertLess(m.ar_worst_db, 1.5)
        self.assertEqual(m.hand, "rhcp")

    def test_q_matches_jackson_for_a_plain_patch(self):
        c = config()
        L, W, h = 60.0, 36.0, c.patch_height_mm()
        cav = Cavity.build(Shape(rect(L, W), 0, 0, ((10, 0),), W), c)
        q = next(m["q_rad"] for m in cav.mode_table(47.0) if m["kind"].startswith("broadside"))
        lam0 = 299.792458 / (cav.f_modes[1] / 1e9)
        er = c.epsilon_eq()
        c1 = 1 - 1 / er + 2 / (5 * er**2)
        jackson = 3 / 16 * er / c1 * (L / W) * (lam0 / h)
        self.assertLess(abs(math.log(q / jackson)), math.log(1.6))


if __name__ == "__main__":
    unittest.main()
