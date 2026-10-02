# SPDX-License-Identifier: MIT
import tempfile
import unittest
from pathlib import Path

from antenna_testkit import config
from bac_antenna.core import MockBackend, optimise, score
from bac_antenna.metrics import BandMetrics, Metrics
from bac_antenna.rf import axial_ratio_db, circular_components, rotation_sense


def metrics(tx: BandMetrics, f=2.245e9):
    other = BandMetrics(-20, 5, 1, 90, "rhcp")
    return Metrics({"tx": tx, "rx": other, "s2400": other}, f)


class CoreTests(unittest.TestCase):
    def test_score_zero_when_targets_met(self):
        self.assertEqual(score(metrics(BandMetrics(-15, 7, 2, 90, "rhcp")), config()), 0.0)

    def test_score_penalises_each_shortfall(self):
        c = config()
        base = score(metrics(BandMetrics(-15, 7, 2, 90, "rhcp")), c)
        for bad in (
            BandMetrics(-5, 7, 2, 90, "rhcp"),
            BandMetrics(-15, 2, 2, 90, "rhcp"),
            BandMetrics(-15, 7, 8, 90, "rhcp"),
            BandMetrics(-15, 7, 2, 40, "rhcp"),
        ):
            self.assertGreater(score(metrics(bad), c), base)
        self.assertGreater(score(metrics(BandMetrics(-15, 7, 2, 90, "rhcp"), f=2.0e9), c), base)

    def test_zero_weight_band_is_not_scored(self):
        c = config()
        m = Metrics(
            {
                "tx": BandMetrics(-15, 7, 2, 90, "rhcp"),
                "rx": BandMetrics(-20, 5, 1, 90, "rhcp"),
                "s2400": BandMetrics(0, -20, 40, 5, "lhcp"),
            },
            2.245e9,
        )
        self.assertEqual(score(m, c), 0.0)

    def test_polarization_helpers(self):
        self.assertAlmostEqual(axial_ratio_db(1, -1j), 0.0, places=8)
        er, el = circular_components(1, -1j)  # IEEE RHCP for +z
        self.assertGreater(abs(er), 10 * abs(el))
        self.assertEqual(rotation_sense(1, -1j), 1)
        self.assertEqual(rotation_sense(1, 1j), -1)

    def test_overrides(self):
        c = config("cross_2200.toml", "band.tx.cp_span_hz=10e6", 'feed.mode="dual"')
        self.assertEqual(c.primary_band.cp_span_hz, 10e6)
        self.assertEqual(c.feed["mode"], "dual")

    def test_mock_optimiser_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            results = optimise(config(), MockBackend(), Path(temp), runs=8)
            self.assertEqual(len(results), 8)
            self.assertTrue((Path(temp) / "summary.csv").exists())
            self.assertTrue((results[0].directory / "geometry.vtp").exists())


if __name__ == "__main__":
    unittest.main()
