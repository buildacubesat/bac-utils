import math
import unittest

from bac_antenna.geometry import check_model, cross_outline, ring_outline, winding, with_hole
from bac_antenna.topologies import CrossPatch, AnnularRing
from helpers import NOMINAL, config


class GeometryTests(unittest.TestCase):
    def test_cross_with_hole_inside_test(self):
        pts = with_hole(cross_outline(70, 66, 34), 6.0)
        self.assertEqual(winding(pts, 0, 0), 0)            # bore
        self.assertEqual(winding(pts, -3, 0.0), 0)         # bore, on the seam line
        self.assertNotEqual(winding(pts, 20, 0), 0)        # x arm
        self.assertNotEqual(winding(pts, 0, -25), 0)       # y arm
        self.assertEqual(winding(pts, 25, 25), 0)          # between arms
        self.assertEqual(winding(pts, 36, 0), 0)           # beyond x tip

    def test_ring_outline_tab(self):
        pts = ring_outline(16.0, 3.0, 3.0)
        self.assertNotEqual(winding(pts, 18.0, 0.0), 0)
        self.assertEqual(winding(pts, 18.0, 2.5), 0)

    def test_models_are_clean(self):
        for short in ("true", "false"):
            for mode in ('"single"', '"dual"'):
                c = config("cross_2200.toml", f"outline.bore_short={short}", f"feed.mode={mode}")
                m = CrossPatch().model(NOMINAL, c)
                self.assertEqual(check_model(m), [])
                self.assertEqual(len(m.ports), 2 if "dual" in mode else 1)
                tube = next(p for p in m.primitives if p.prop == "camera_tube")
                bore = next(p for p in m.primitives if p.prop == "optical_bore")
                self.assertLess(bore.start[2], tube.start[2])
                self.assertGreater(bore.stop[2], c.patch_height_mm())
                self.assertAlmostEqual(tube.stop[2], c.patch_height_mm() if short == "true" else 0.0)

    def test_feed_clears_sleeve_and_sits_under_copper(self):
        c = config()
        t = CrossPatch()
        self.assertTrue(t.valid(NOMINAL, c))
        self.assertFalse(t.valid(dict(NOMINAL, feed_offset_mm=8.0), c))      # SMP would hit the sleeve
        self.assertFalse(t.valid(dict(NOMINAL, arm_x_mm=79.0), c))           # beyond the board
        for fx, fy in t.shape(NOMINAL, c).feeds:
            self.assertGreaterEqual(math.hypot(fx, fy), float(c.feed["min_offset_mm"]))

    def test_stack_limit(self):
        with self.assertRaises(ValueError):
            config("cross_2200.toml", "stack.gap_mm=5.0")

    def test_ring_topology(self):
        c = config("annular_2200.toml")
        p = dict(outer_radius_mm=24.0, feed_offset_mm=14.0, perturbation_mm=2.0, pad_radius_mm=2.0)
        self.assertTrue(AnnularRing().valid(p, c))
        self.assertEqual(check_model(AnnularRing().model(p, c)), [])
