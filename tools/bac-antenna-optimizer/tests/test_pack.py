# SPDX-License-Identifier: MIT
"""`bac-antenna pack`: case matching by effective state, plan for missing levels, pack files."""

import gzip
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from antenna_testkit import ROOT
from bac_antenna.pack import build_pack
from bac_antenna.sweep import run_sweep


class PackTests(unittest.TestCase):
    def test_pack_from_cavity_cases(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "design").mkdir()
            (root / "design" / "plans").mkdir()
            (root / "sim" / "runs").mkdir(parents=True)
            shutil.copy(ROOT / "config" / "cross_2200_dual_v2.toml", root / "design" / "2200.toml")
            shutil.copy(ROOT / "designs" / "cross_2200_dual_v2.json", root / "design" / "2200.json")
            (root / "plan.toml").write_text(
                '[[case]]\nname = "ref-2200"\n[[case]]\nname = "gap_4.37"\nset = ["geometry.stack.gap_mm=4.37"]\n'
                '[[case]]\nname = "gap_5.27"\nset = ["geometry.stack.gap_mm=5.27", "geometry.stack.max_height_mm=7.0"]\n'
                '[[case]]\nname = "other_stack"\nset = ["geometry.stack.gap_mm=4.37", "geometry.stack.top_board_mm=0.6"]\n'
            )
            run_sweep(
                root / "design" / "2200.toml",
                root / "design" / "2200.json",
                root / "plan.toml",
                root / "sim" / "runs",
                "cavity",
                [],
                False,
            )
            (root / "design" / "sensitivity.toml").write_text("""
[sensitivity]
name = "test"
config = "design/2200.toml"
design = "design/2200.json"
nominal = "sim/runs/ref-2200"
runs = ["sim/runs"]
ignore = ["geometry.stack.max_height_mm"]
[[axis]]
id = "gap"
label = "Air gap"
unit = "mm"
set = "geometry.stack.gap_mm"
levels = [4.37, 4.67, 4.97, 5.27]
also = ["geometry.stack.max_height_mm=7.0"]
[[axis]]
id = "arms"
params = ["arm_x_mm", "arm_y_mm"]
levels = [60.2, 60.7]
""")
            self.assertEqual(build_pack(root / "design" / "sensitivity.toml"), 0)
            pack = json.loads((root / "generated" / "sensitivity" / "pack.json").read_text())
            gap = next(a for a in pack["axes"] if a["id"] == "gap")
            by_level = {x["level"]: x["case"] for x in gap["levels"]}
            self.assertEqual(by_level[4.67], "nominal")
            self.assertEqual(by_level[4.37], "gap_4.37")  # matched, and not the other-stack case
            self.assertEqual(by_level[5.27], "gap_5.27")  # max_height override ignored in matching
            self.assertIsNone(by_level[4.97])
            self.assertEqual(gap["missing"], [4.97])
            plan = (root / "design" / "plans" / "sensitivity.toml").read_text()
            self.assertIn('name = "gap_4.97"', plan)
            self.assertIn("geometry.stack.max_height_mm=7.0", plan)  # the axis' `also` overrides travel with the plan
            self.assertIn('name = "arms_60.2"', plan)
            with gzip.open(root / "generated" / "sensitivity" / "cases.csv.gz", "rt") as fh:
                header = fh.readline().strip().split(",")
            self.assertIn("axis:gap", header)
            self.assertIn("tx_gain_min_dbic", header)
            self.assertTrue((root / "generated" / "sensitivity" / "config.toml").exists())
            models = json.loads((root / "generated" / "sensitivity" / "models.json").read_text())
            self.assertIn("gap_4.37", models)


if __name__ == "__main__":
    unittest.main()
