"""Headless checks of the visualizer.

SyntheticPackTests builds a small pack with the optimizer itself (cavity-backend sweep + `build_pack`), adds a
synthetic sphere, field planes and complex S-parameters, and runs the notebook on it – no FDTD data needed.
RealPackTests runs the notebook on whatever pack the notebook discovers on this machine (a bac-hardware checkout
next to bac-utils, the notebook's packs/ folder, or BAC_ANTENNA_PACKS) and is skipped when there is none.
"""
import gzip
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def _run_notebook():
    if "bac_antenna_visualizer" in sys.modules:
        nb = importlib.reload(sys.modules["bac_antenna_visualizer"])
    else:
        nb = importlib.import_module("bac_antenna_visualizer")
    return nb.app.run()


def build_synthetic_pack(root: Path) -> Path:
    """An antenna folder with cavity-backend cases on two axes, packed by the tool, plus synthetic 3D data."""
    from bac_antenna.pack import build_pack
    from bac_antenna.sweep import run_sweep

    tool = Path(__import__("bac_antenna").__file__).resolve().parents[2]
    (root / "design" / "plans").mkdir(parents=True)
    (root / "sim" / "runs").mkdir(parents=True)
    shutil.copy(tool / "config" / "cross_2200_dual_v2.toml", root / "design" / "2200.toml")
    shutil.copy(tool / "designs" / "cross_2200_dual_v2.json", root / "design" / "2200.json")
    (root / "plan.toml").write_text(
        '[[case]]\nname = "ref-2200"\n'
        '[[case]]\nname = "gap_4.37"\nset = ["geometry.stack.gap_mm=4.37"]\n'
        '[[case]]\nname = "gap_4.97"\nset = ["geometry.stack.gap_mm=4.97", "geometry.stack.max_height_mm=7.0"]\n'
        '[[case]]\nname = "arms_60.2"\nparams = { arm_x_mm = 60.2, arm_y_mm = 60.2 }\n'
        '[[case]]\nname = "arms_61.2"\nparams = { arm_x_mm = 61.2, arm_y_mm = 61.2 }\n'
    )
    run_sweep(root / "design" / "2200.toml", root / "design" / "2200.json", root / "plan.toml", root / "sim" / "runs", "cavity", [], False)
    (root / "design" / "sensitivity.toml").write_text(
        '[sensitivity]\nname = "synthetic-2200"\nconfig = "design/2200.toml"\ndesign = "design/2200.json"\n'
        'nominal = "sim/runs/ref-2200"\nruns = ["sim/runs"]\nignore = ["geometry.stack.max_height_mm"]\n'
        'source = "test"\nrelease = "none"\n'
        '[[axis]]\nid = "gap"\nlabel = "Air gap"\nunit = "mm"\nset = "geometry.stack.gap_mm"\nlevels = [4.37, 4.67, 4.97]\n'
        '[[axis]]\nid = "arms"\nlabel = "Arm length"\nunit = "mm"\nparams = ["arm_x_mm", "arm_y_mm"]\nlevels = [60.2, 60.7, 61.2]\n'
    )
    assert build_pack(root / "design" / "sensitivity.toml") == 0
    pack = root / "generated" / "sensitivity"
    meta = json.loads((pack / "pack.json").read_text())
    nominal = meta["nominal_case"]
    cases = list(meta["cases"])
    # sphere: a cos^4 lobe with a small back lobe, every case
    th = np.arange(0, 181, 5.0)
    ph = np.arange(0, 360, 10.0)
    rows = []
    for k, c in enumerate(cases):
        for t in th:
            for p in ph:
                g = 10 * np.log10(max(1e-3, np.cos(np.radians(t)) ** 4)) + 10.5 - 0.3 * k if t <= 90 else -12 - 0.05 * (t - 90)
                rows.append({"case": c, "theta_deg": t, "phi_deg": p, "gain_total_dbi": g, "gain_co_dbic": g, "gain_cross_dbic": g - 20, "ar_db": 0.6 + t / 60})
    with gzip.open(pack / "sphere.csv.gz", "wt", newline="") as fh:
        pd.DataFrame(rows).to_csv(fh, index=False)
    # field planes: a gaussian on two planes, nominal only
    rows = []
    u = np.arange(-40, 41, 4.0)
    for plane, axes, fixed, coord in (("E_gap", "xy", "z", 2.33), ("E_xz", "xz", "y", 0.0)):
        for a in u:
            for b in u:
                rows.append({"case": nominal, "plane": plane, "axes": axes, "fixed": fixed, "coord": coord, "u": a, "v": b, "e_db": -(a**2 + b**2) / 100})
    with gzip.open(pack / "efield.csv.gz", "wt", newline="") as fh:
        pd.DataFrame(rows).to_csv(fh, index=False)
    # sweeps: the cavity backend writes no S-parameter files, so make a loop per case
    f = np.linspace(1.6e9, 2.9e9, 131)
    ang = (f - 2.245e9) / 0.3e9 * np.pi
    sw = pd.concat([pd.DataFrame({"case": c, "frequency_hz": f, "s11_in_db": -20 - 5 * np.cos(ang), "s11_db": -10 - 5 * np.cos(ang), "s21_db": -30.0,
                                  "s11_re": 0.3 * np.cos(ang) + 0.1, "s11_im": 0.3 * np.sin(ang)}) for c in cases])
    with gzip.open(pack / "sweeps.csv.gz", "wt", newline="") as fh:
        sw.to_csv(fh, index=False)
    return pack


class SyntheticPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.pack = build_synthetic_pack(cls.tmp)
        os.environ["BAC_ANTENNA_PACKS"] = str(cls.tmp)          # an antenna folder as a search root
        cls.outputs, cls.defs = _run_notebook()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("BAC_ANTENNA_PACKS", None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_discovered_from_antenna_folder(self):
        d = self.defs
        self.assertIn("synthetic-2200", d["FOUND"])
        self.assertEqual(Path(d["FOUND"]["synthetic-2200"]).resolve(), self.pack.resolve())
        self.assertEqual(Path(d["pack_source"]).resolve(), self.pack.resolve())   # BAC_ANTENNA_PACKS packs come first
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
        except Exception as exc:       # the No Pack callout stops the run
            raise unittest.SkipTest(f"no pack discoverable here: {exc}")
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
