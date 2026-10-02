from pathlib import Path
import tempfile
import unittest

from bac_antenna.sweep import append_row, read_summary, run_sweep
from helpers import ROOT

PLAN = """
[[case]]
name = "a"
[[case]]
name = "b"
set = ["stack.gap_mm=4.4"]
params = { arm_x_mm = 60.5 }
"""


class SweepTests(unittest.TestCase):
    def test_append_keeps_existing_header(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sweep_summary.csv"
            append_row(path, {"case": "x", "score": "0", "tx_gain": "9.7"})
            append_row(path, {"case": "y", "score": "0", "tx_gain": "9.8", "fb_db": "20.0"})   # extra column ignored
            append_row(path, {"case": "z", "score": "0"})                                    # missing column blank
            fields, rows = read_summary(path)
            self.assertEqual(fields, ["case", "score", "tx_gain"])
            self.assertEqual([r["case"] for r in rows], ["x", "y", "z"])
            self.assertEqual(rows[2]["tx_gain"], "")

    def test_cavity_sweep_and_reprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "runs"
            plan = Path(temp) / "plan.toml"
            plan.write_text(PLAN)
            cfg, des = ROOT / "config" / "cross_2200_dual_v2.toml", ROOT / "designs" / "cross_2200_dual_v2.json"
            self.assertEqual(run_sweep(cfg, des, plan, out, "cavity", []), 0)
            fields, rows = read_summary(out / "sweep_summary.csv")
            self.assertEqual([r["case"] for r in rows], ["a", "b"])
            self.assertIn("probe_res_hz", fields)
            self.assertIn("tx_gain_60", fields)
            self.assertEqual(rows[1]["arm_x_mm"], "60.500")
            # resumable: nothing is re-run, nothing is duplicated
            self.assertEqual(run_sweep(cfg, des, plan, out, "cavity", []), 0)
            self.assertEqual(len(read_summary(out / "sweep_summary.csv")[1]), 2)
            # reprocess replaces rows in place instead of appending
            self.assertEqual(run_sweep(cfg, des, plan, out, "cavity", [], reprocess=True), 0)
            fields2, rows2 = read_summary(out / "sweep_summary.csv")
            self.assertEqual([r["case"] for r in rows2], ["a", "b"])
            self.assertEqual(fields2, fields)


if __name__ == "__main__":
    unittest.main()
