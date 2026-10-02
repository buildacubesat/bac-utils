# SPDX-License-Identifier: MIT
"""Pattern post-processing checked against a crossed Huygens source: perfect CP in every direction,
E ~ cos^2(theta/2), directivity exactly 3 (4.77 dBi), 1/8 of the power in the rear hemisphere, and
-2.50 dB at 60 deg off axis."""

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from bac_antenna.pattern import (
    ETA0,
    angular_metrics,
    back_fraction,
    cut_summary,
    read_cuts_csv,
    signed_cut,
    write_cuts_csv,
)


def huygens(theta_deg, phi_deg, hand=+1, amplitude=1.0):
    """(E_theta, E_phi) on a [theta, phi] grid. hand=+1 is RHCP in rf.circular_components' convention
    (E = theta_hat - j phi_hat), hand=-1 LHCP. Returns the fields and the exact radiated power."""
    th = np.radians(np.asarray(theta_deg, dtype=float))[:, None]
    ph = np.zeros(len(phi_deg))[None, :]
    a = amplitude * np.cos(th / 2) ** 2 * np.ones_like(ph)
    et = a.astype(complex)
    ep = (-1j * hand) * a
    # |E|^2 = 2 a^2 cos^4(theta/2); the integral of cos^4(theta/2) over the sphere is 4pi/3
    p_rad = 2 * amplitude**2 / (2 * ETA0) * 4 * math.pi / 3
    return et, ep, p_rad


class PatternTests(unittest.TestCase):
    theta = np.arange(0.0, 181.0, 1.0)
    phi = np.array([0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0])

    def test_huygens_gain_ar_and_hand(self):
        et, ep, p_rad = huygens(self.theta, self.phi)
        m = angular_metrics(et, ep, p_rad, sense=1, wanted="rhcp")
        i0 = 0
        self.assertAlmostEqual(m["gain_co_dbic"][i0, 0], 10 * math.log10(3), places=6)
        self.assertLess(m["gain_cross_dbic"][i0, 0], -50)
        # perfect CP everywhere except the null at 180 deg
        self.assertLess(np.max(m["ar_db"][:-1]), 1e-6)
        i60 = int(np.argmin(np.abs(self.theta - 60)))
        self.assertAlmostEqual(
            m["gain_co_dbic"][i60, 3] - m["gain_co_dbic"][i0, 0], 40 * math.log10(math.cos(math.radians(30))), places=6
        )
        # the same field is LHCP when the sense is mirrored, or when the wanted hand is the other one
        m2 = angular_metrics(et, ep, p_rad, sense=-1, wanted="rhcp")
        self.assertLess(m2["gain_co_dbic"][i0, 0], -50)
        m3 = angular_metrics(et, ep, p_rad, sense=1, wanted="lhcp")
        self.assertLess(m3["gain_co_dbic"][i0, 0], -50)
        # uncalibrated: co is the larger component
        m4 = angular_metrics(et, ep, p_rad, sense=0, wanted="rhcp")
        self.assertAlmostEqual(m4["gain_co_dbic"][i0, 0], 10 * math.log10(3), places=6)

    def test_realized_gain_includes_loss(self):
        et, ep, p_rad = huygens(self.theta, self.phi)
        m = angular_metrics(et, ep, 2 * p_rad, sense=1, wanted="rhcp")  # half the incident power radiates
        self.assertAlmostEqual(m["gain_co_dbic"][0, 0], 10 * math.log10(3) - 10 * math.log10(2), places=6)

    def test_summary_and_front_to_back(self):
        et, ep, p_rad = huygens(self.theta, self.phi)
        s = cut_summary(self.theta, angular_metrics(et, ep, p_rad, sense=1, wanted="rhcp"))
        self.assertAlmostEqual(
            s["gain_co_min_60"], 10 * math.log10(3) + 40 * math.log10(math.cos(math.radians(30))), places=6
        )
        self.assertAlmostEqual(
            s["gain_co_min_45"], 10 * math.log10(3) + 40 * math.log10(math.cos(math.radians(22.5))), places=6
        )
        self.assertLess(s["ar_max_60"], 1e-6)
        self.assertGreater(s["front_to_back_db"], 60)  # exact null behind, clamped at the gain floor
        self.assertTrue(s["theta_180_reached"])
        # a source with a real back lobe: add a small isotropic LHCP term behind
        et2, ep2 = et.copy(), ep.copy()
        back = self.theta[:, None] > 90
        et2 = np.where(back, et2 + 0.1, et2)
        ep2 = np.where(back, ep2 + 0.1j, ep2)
        s2 = cut_summary(self.theta, angular_metrics(et2, ep2, p_rad, sense=1, wanted="rhcp"))
        self.assertAlmostEqual(s2["front_to_back_db"], 20 * math.log10(1 / 0.1), places=6)

    def test_back_fraction_matches_closed_form(self):
        theta = np.arange(0.0, 181.0, 5.0)
        phi = np.arange(0.0, 360.0, 10.0)
        et, ep, _ = huygens(theta, phi)
        self.assertAlmostEqual(back_fraction(et, ep, theta, phi), 1 / 8, delta=0.003)

    def test_csv_round_trip_and_signed_cut(self):
        et, ep, p_rad = huygens(self.theta, self.phi)
        m = angular_metrics(et, ep, p_rad, sense=1, wanted="rhcp")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "farfield_cuts.csv"
            write_cuts_csv(path, [2.2e9, 2.245e9], self.theta, self.phi, [m, m])
            back = read_cuts_csv(path)
        self.assertEqual(back["freqs"], [2.2e9, 2.245e9])
        np.testing.assert_allclose(back["metrics"][1]["gain_co_dbic"], np.round(m["gain_co_dbic"], 2), atol=1e-9)
        xs, ys = signed_cut(back["theta"], back["phi"], back["metrics"][0]["gain_co_dbic"], 90.0)
        self.assertEqual(xs[0], -180.0)
        self.assertEqual(xs[-1], 180.0)
        self.assertEqual(len(xs), 2 * len(self.theta) - 1)
        self.assertAlmostEqual(ys[int(np.argmin(np.abs(xs)))], round(10 * math.log10(3), 2), places=9)


if __name__ == "__main__":
    unittest.main()
