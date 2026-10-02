# SPDX-License-Identifier: MIT
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from antenna_testkit import ROOT
from bac_antenna.report.manifest import band_values, render, resolve, run_report


class TemplateTests(unittest.TestCase):
    def test_render_resolves_nested_keys_and_marks_missing(self):
        ctx = {"name": "A", "2200": {"gain_min": "10.20"}}
        missing = []
        out = render("{{ name }}: {{ 2200.gain_min }} dBic, {{ 2400.gain_min }}", ctx, missing)
        self.assertEqual(out, "A: 10.20 dBic, –")
        self.assertEqual(missing, ["2400.gain_min"])
        self.assertIsNone(resolve(ctx, "2200.nothing"))


class ManifestTests(unittest.TestCase):
    def _folder(self, temp: Path) -> Path:
        (temp / "design").mkdir()
        shutil.copy(ROOT / "config" / "cross_2200_dual_v2.toml", temp / "design" / "2200.toml")
        shutil.copy(ROOT / "designs" / "cross_2200_dual_v2.json", temp / "design" / "2200.json")
        runs = temp / "sim" / "runs" / "freeze" / "frozen"
        runs.mkdir(parents=True)
        (runs / "result.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "bands": {
                            "tx": {
                                "s11_worst_db": -26.9,
                                "gain_min_dbic": 10.2,
                                "ar_worst_db": 0.66,
                                "efficiency_percent": 93.5,
                                "hand": "rhcp",
                            }
                        }
                    }
                }
            )
        )
        (runs / "openems_diagnostics.json").write_text(
            json.dumps(
                {
                    "probe_resonance_hz": 2.2468e9,
                    "hybrid_load_fraction_at_primary_centre": 0.032,
                    "per_port_at_primary_centre": {"s11_db": -15.0},
                }
            )
        )
        (temp / "templates").mkdir()
        (temp / "templates" / "README.md").write_text(
            "# {{ name }}\n\ngain {{ 2200.gain_min }} dBic, probe {{ 2200.probe_res_ghz }} GHz, load {{ 2200.load_pct }} %, arms {{ 2200.arm }}, stack {{ stack }} mm, missing {{ 2200.g60 }}\n"
        )
        (temp / "antenna.toml").write_text("""[antenna]
name = "test antenna"
tool_tag = "v0"
[bands.2200]
label = "2200"
config = "design/2200.toml"
design = "design/2200.json"
reference_run = "sim/runs/freeze/frozen"
[output]
generated = "generated"
[[documents]]
template = "templates/README.md"
output = "README.md"
""")
        return temp

    def test_docs_from_manifest_without_matplotlib(self):
        with tempfile.TemporaryDirectory() as t:
            temp = self._folder(Path(t))
            self.assertEqual(run_report(temp / "antenna.toml", skip={"drawings", "charts", "boards"}), 0)
            readme = (temp / "README.md").read_text()
            self.assertIn("gain 10.20 dBic", readme)
            self.assertIn("probe 2.2468 GHz", readme)
            self.assertIn("load 3.2 %", readme)
            self.assertIn("arms 60.7", readme)
            self.assertIn("stack 5.99 mm", readme)
            self.assertIn("missing –", readme)
            status = (temp / "generated" / "STATUS.md").read_text()
            self.assertIn("bac-antenna report antenna.toml", status)
            self.assertTrue((temp / "generated" / "values.json").exists())

    def test_values_from_summary_row_when_result_json_missing(self):
        with tempfile.TemporaryDirectory() as t:
            temp = self._folder(Path(t))
            case = temp / "sim" / "runs" / "freeze" / "frozen"
            (case / "result.json").unlink()
            (case.parent / "sweep_summary.csv").write_text(
                "case,tx_s11,tx_gain,tx_ar,tx_eff,tx_hand\nfrozen,-26.87,10.20,0.66,93.5,rhcp\n"
            )
            v = band_values(
                temp,
                "2200",
                {"config": "design/2200.toml", "design": "design/2200.json", "reference_run": "sim/runs/freeze/frozen"},
                {"order_scale": 1.03},
            )
            self.assertEqual(v["gain_min"], "10.20")
            self.assertEqual(v["rl_min"], "26.9")
            self.assertEqual(v["available"], "yes")


if __name__ == "__main__":
    unittest.main()


class ExporterTests(unittest.TestCase):
    """The patch exporters must accept the 0.6 [geometry] layout (and the legacy one)."""

    def test_drawings_and_boards_on_migrated_config(self):
        from bac_antenna.report.drawings import draw_all
        from bac_antenna.report.kicad import make_boards

        cfg = ROOT / "config" / "cross_2200_dual_v2.toml"
        des = ROOT / "designs" / "cross_2200_dual_v2.json"
        with tempfile.TemporaryDirectory() as t:
            files = draw_all(cfg, des, Path(t) / "d" / "2200", title="t")
            self.assertTrue(any(f.endswith("_ground.svg") for f in files))
            boards = make_boards(cfg, {"2200": des}, Path(t) / "b")
            self.assertEqual(boards, ["ground_board.kicad_pcb", "patch_board_2200.kicad_pcb"])
            self.assertIn("(kicad_pcb", (Path(t) / "b" / "ground_board.kicad_pcb").read_text()[:20])


class IdempotencyTests(unittest.TestCase):
    """Regenerating an unchanged design must reproduce the board files byte for byte."""

    def test_boards_are_deterministic(self):
        from bac_antenna.report.kicad import make_boards

        cfg = ROOT / "config" / "cross_2200_dual_v2.toml"
        des = ROOT / "designs" / "cross_2200_dual_v2.json"
        with tempfile.TemporaryDirectory() as t:
            outs = []
            for i in (1, 2):
                make_boards(cfg, {"2200": des}, Path(t) / f"b{i}")
                outs.append((Path(t) / f"b{i}" / "ground_board.kicad_pcb").read_bytes())
            self.assertEqual(outs[0], outs[1])
            self.assertIn("6f2a1c0e", str(__import__("bac_antenna.report.kicad", fromlist=["_UID_NS"])._UID_NS))
