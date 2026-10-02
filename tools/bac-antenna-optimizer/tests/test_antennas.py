# SPDX-License-Identifier: MIT
"""Antenna types, feed networks, config layouts and migration."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from antenna_testkit import ROOT
from bac_antenna.antennas import builtin_types, get_antenna
from bac_antenna.config import load_config
from bac_antenna.core import full_params
from bac_antenna.feednetwork import weight_options
from bac_antenna.geometry import check_model
from bac_antenna.migrate import migrate_config_text, migrate_plan_text
from bac_antenna.openems_backend import build_lines

GENERIC = """
[[band]]
name = "uhf"
low_hz = 4.30e8
high_hz = 4.40e8
weight = 1.0
max_s11_db = -10.0
min_gain_dbic = 0.0
max_ar_db = 3.0
[polarization]
hand = "rhcp"
[optimizer]
runs = 10
[mesh]
excitation_low_hz = 3.0e8
excitation_high_hz = 6.0e8
frequency_points = 201
cells_per_wavelength = 20
air_margin_mm = 200.0
boundary = "MUR"
timesteps = 100000
end_criteria = 1e-4
mesh_growth = 1.4
[weights]
s11 = 1.0
"""


def write(temp: Path, name: str, text: str) -> Path:
    p = temp / name
    p.write_text(text)
    return p


class TypeTests(unittest.TestCase):
    def test_builtins_registered(self):
        self.assertEqual(set(builtin_types()), {"cross_patch", "annular_ring", "dipole", "turnstile"})

    def test_dipole_model(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = write(
                Path(t),
                "d.toml",
                '[antenna]\ntype = "dipole"\n[geometry]\nstrip_width_mm = 2.0\ngap_mm = 1.0\n[search]\nlength_mm = [250.0, 400.0]\n'
                + GENERIC,
            )
            config = load_config(cfg)
            ant = get_antenna(config)
            self.assertFalse(ant.has_estimator())
            p = full_params({"length_mm": 320.0}, config)
            self.assertTrue(ant.valid(p, config))
            m = ant.model(p, config)
            self.assertEqual(check_model(m), [])
            self.assertEqual(len(m.ports), 1)
            self.assertEqual(m.extent(), (-160.0, 160.0, -1.0, 1.0, 0.0, 0.0))
            self.assertEqual(len(weight_options(config, 1)), 1)
            dom = {"x": (-360.0, 360.0), "y": (-201.0, 201.0), "z": (-200.0, 200.0)}
            lines = build_lines(m, config.mesh, dom)
            for v in (-160.0, -0.5, 0.5, 160.0):
                self.assertIn(v, lines["x"])
            self.assertIn(0.0, lines["z"])

    def test_turnstile_model_and_feed(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = write(
                Path(t),
                "t.toml",
                '[antenna]\ntype = "turnstile"\n[geometry]\nbody_x_mm = 100.0\nbody_y_mm = 100.0\nbody_z_mm = 340.0\n'
                "tape_width_mm = 3.0\ntape_thickness_mm = 0.1\nelement_height_mm = 3.0\nroot_inset_mm = 5.0\n[search]\nelement_length_mm = [140.0, 200.0]\n"
                + GENERIC,
            )
            config = load_config(cfg)
            ant = get_antenna(config)
            p = full_params({"element_length_mm": 170.0}, config)
            m = ant.model(p, config)
            self.assertEqual(check_model(m), [])
            self.assertEqual(len(m.ports), 4)
            self.assertEqual([q.direction for q in m.ports], ["z"] * 4)
            self.assertEqual(m.extent()[0], -215.0)  # 50 - 5 + 170 reach
            opts = weight_options(config, 4)
            self.assertEqual(len(opts), 2)
            for a in opts:
                self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0)
                self.assertAlmostEqual(a[2] / a[0], -1.0)  # opposite elements anti-phase
                self.assertAlmostEqual(abs(a[1] / a[0]), 1.0)
                self.assertAlmostEqual(abs(np.angle(a[1] / a[0])), np.pi / 2)

    def test_file_type(self):
        with tempfile.TemporaryDirectory() as t:
            temp = Path(t)
            write(
                temp,
                "mine.py",
                "from bac_antenna.antennas.dipole import Dipole\n\nclass Mine(Dipole):\n    name = 'mine'\n\nANTENNA = Mine()\n",
            )
            cfg = write(
                temp,
                "m.toml",
                f'[antenna]\ntype = "file:{temp / "mine.py"}"\n[geometry]\nstrip_width_mm = 2.0\ngap_mm = 1.0\n[search]\nlength_mm = [250.0, 400.0]\n'
                + GENERIC,
            )
            self.assertEqual(get_antenna(load_config(cfg)).name, "mine")

    def test_feed_network_custom_and_errors(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = write(
                Path(t),
                "d.toml",
                '[antenna]\ntype = "dipole"\n[geometry]\nstrip_width_mm = 2.0\ngap_mm = 1.0\n[search]\nlength_mm = [250.0, 400.0]\n'
                '[feed_network]\nmode = "custom"\nweights = [[1.0, 0.0], [0.0, -1.0]]\n' + GENERIC,
            )
            config = load_config(cfg)
            a = weight_options(config, 2)[0]
            self.assertAlmostEqual(a[1] / a[0], -1j)
            with self.assertRaises(ValueError):
                weight_options(config, 3)


class LayoutTests(unittest.TestCase):
    def test_legacy_and_migrated_configs_build_the_same_model(self):
        legacy = Path("/tmp/config_05/cross_2200_dual_v2.toml")
        if not legacy.exists():
            self.skipTest("0.5 config copy not present")
        new = ROOT / "config" / "cross_2200_dual_v2.toml"
        design = json.loads((ROOT / "designs" / "cross_2200_dual_v2.json").read_text())
        models = []
        for path in (legacy, new):
            config = load_config(path, ["stack.gap_mm=4.5"])  # legacy override spelling on both layouts
            self.assertEqual(float(config.stack["gap_mm"]), 4.5)
            models.append(get_antenna(config).model(full_params(design, config), config))
        self.assertEqual(models[0], models[1])

    def test_migrate_text(self):
        src = '[project]\nname = "x"\ntopology = "cross_patch"\n[polarization]\nhand = "rhcp"\nhybrid_phase_deg = 86.0\n[stack]\ngap_mm = 4.0\n[feed]\nmode = "dual"\n'
        out = migrate_config_text(src)
        self.assertIn('[antenna]\ntype = "cross_patch"', out)
        self.assertIn("[geometry.stack]", out)
        self.assertIn("[geometry.feed]", out)
        self.assertNotIn("topology =", out)
        self.assertIn("phase_error_deg = -4", out)
        self.assertEqual(migrate_config_text(out), out)  # idempotent
        plan = 'set = ["stack.gap_mm=4.1", "outline.ground=\\"panel\\"", "polarization.hybrid_phase_deg=86"]'
        self.assertEqual(
            migrate_plan_text(plan),
            'set = ["geometry.stack.gap_mm=4.1", "geometry.outline.ground=\\"panel\\"", "polarization.hybrid_phase_deg=86"]',
        )

    def test_feed_network_maps_legacy_keys(self):
        config = load_config(
            ROOT / "config" / "cross_2200_dual_v2.toml",
            ["polarization.hybrid_phase_deg=94", "polarization.hybrid_amplitude_db=0.3"],
        )
        self.assertAlmostEqual(config.feed_network["phase_error_deg"], 4.0)
        self.assertAlmostEqual(config.feed_network["amplitude_error_db"], 0.3)
        opts = weight_options(config, 2)
        self.assertEqual(len(opts), 2)


if __name__ == "__main__":
    unittest.main()
