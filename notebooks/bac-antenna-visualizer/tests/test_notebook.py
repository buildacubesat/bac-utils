# SPDX-License-Identifier: MIT
"""Headless checks of the visualizer.

SyntheticPackTests builds a small pack with the optimizer itself (cavity-backend sweep + `build_pack`), adds a
synthetic sphere, field planes and complex S-parameters, and runs the notebook on it – no FDTD data needed.
RealPackTests runs the notebook on whatever pack the notebook discovers on this machine (a bac-hardware checkout
next to bac-utils, the notebook's packs/ folder, or BAC_ANTENNA_PACKS) and is skipped when there is none.
"""

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from visualizer_testkit import build_synthetic_pack

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def _run_notebook():
    if "bac_antenna_visualizer" in sys.modules:
        nb = importlib.reload(sys.modules["bac_antenna_visualizer"])
    else:
        nb = importlib.import_module("bac_antenna_visualizer")
    return nb.app.run()


class SyntheticPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.pack = build_synthetic_pack(cls.tmp)
        os.environ["BAC_ANTENNA_PACKS"] = str(cls.tmp)  # an antenna folder as a search root
        cls.outputs, cls.defs = _run_notebook()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("BAC_ANTENNA_PACKS", None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_discovered_from_antenna_folder(self):
        d = self.defs
        self.assertIn("synthetic-2200", d["FOUND"])
        self.assertEqual(Path(d["FOUND"]["synthetic-2200"]).resolve(), self.pack.resolve())
        self.assertEqual(Path(d["pack_source"]).resolve(), self.pack.resolve())  # BAC_ANTENNA_PACKS packs come first
        self.assertEqual(d["MODE"], "nominal")
        self.assertEqual(d["PACK"]["meta"]["source"], "test")

    def test_interpolation_and_clamping(self):
        d = self.defs
        (l0, c0), (l1, c1) = d["axis_cases"]("gap")[:2]
        mid = (l0 + l1) / 2
        a, b = d["CASES"].loc[c0, "resonance_hz"], d["CASES"].loc[c1, "resonance_hz"]
        self.assertAlmostEqual(d["scalars_at"]("gap", mid)["resonance_hz"], (a + b) / 2, places=3)
        self.assertEqual(d["bracket"]("gap", l0 - 100)[2], 0.0)

    def test_tables_blend_and_fall_back(self):
        d = self.defs
        (l0, c0), (l1, c1) = d["axis_cases"]("gap")[:2]
        mid = (l0 + l1) / 2
        sph, note = d["blend_table"](d["PACK"]["sphere"], ["theta_deg", "phi_deg"], "gap", mid)
        self.assertGreater(len(sph), 1000)
        self.assertEqual(note, "")
        ef, note2 = d["blend_table"](d["PACK"]["efield"], ["plane", "u", "v"], "gap", mid)
        self.assertGreater(len(ef), 100)
        self.assertTrue(note2.startswith("nearest"))

    def test_smith_table(self):
        d = self.defs
        tbl = d["SMITH_TABLE"]
        self.assertEqual(list(tbl["Point"]), ["band low", "band centre", "band high"])
        for _, r in tbl.iterrows():
            g = complex(r["re"], r["im"])
            z = d["Z0"] * (1 + g) / (1 - g)
            self.assertAlmostEqual(r["R (Ω)"], z.real, places=6)
            self.assertAlmostEqual(r["VSWR"], (1 + abs(g)) / (1 - abs(g)), places=6)

    def test_sensitivity_and_geometry(self):
        d = self.defs
        self.assertGreater(len(d["SENS"]), 0)
        self.assertTrue({"Axis", "Quantity", "Slope", "Worst deviation from a line"} <= set(d["SENS"].columns))
        self.assertTrue(d["GEOMETRY_NOTE"].startswith("Geometry rebuilt"))
        self.assertTrue(any(p["prop"] == "patch" for p in d["GEOMETRY"]))

    def test_zip_pack_loads(self):
        d = self.defs
        import zipfile

        z = self.tmp / "synthetic-pack.zip"
        with zipfile.ZipFile(z, "w") as zf:
            for f in self.pack.iterdir():
                zf.write(f, f"synthetic-2200/{f.name}")
        blobs = d["read_location"](str(z))
        self.assertIn("pack.json", blobs)
        self.assertEqual(d["pack_name_of"](z), "synthetic-2200")


class RealPackTests(unittest.TestCase):
    """The notebook on a pack found on this machine; skipped when none is discoverable."""

    @classmethod
    def setUpClass(cls):
        os.environ.pop("BAC_ANTENNA_PACKS", None)
        try:
            cls.outputs, cls.defs = _run_notebook()
        except Exception as exc:  # the No Pack callout stops the run
            raise unittest.SkipTest(f"no pack discoverable here: {exc}") from exc
        if not cls.defs.get("FOUND"):
            raise unittest.SkipTest("no pack discoverable here")

    def test_full_pack(self):
        d = self.defs
        self.assertEqual(d["MODE"], "nominal")
        self.assertGreater(len(d["PACK"]["sphere"]), 0, "reference run should carry farfield_sphere.csv")
        self.assertEqual(len(d["SMITH_TABLE"]), 3)
        self.assertGreater(len(d["SENS"]), 0)
        self.assertTrue(d["GEOMETRY_NOTE"].startswith("Geometry rebuilt"))


if __name__ == "__main__":
    unittest.main()
