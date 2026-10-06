# SPDX-License-Identifier: MIT
"""Headless checks of the molab demo snapshot (demo/bac_antenna_visualizer_demo.py).

The demo is the visualizer without the optimizer: packs are found beside the file and the geometry comes from
the pack's stored models. SyntheticPackTests copies the demo into a temporary folder next to a synthetic pack
and runs it there; StoredGeometryTests compares the blended stored models with the optimizer's live model, which
is what the tracked notebook shows; RealPackTests runs the demo on the pack zips that sit beside it in the
checkout (not tracked) and is skipped when there are none.
"""

import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

import numpy as np
from visualizer_testkit import build_synthetic_pack

HERE = Path(__file__).resolve().parents[1]
DEMO = HERE / "demo" / "bac_antenna_visualizer_demo.py"
NOTEBOOK = HERE / "bac_antenna_visualizer.py"


def _run_demo(folder: Path):
    """Import the demo from `folder` (a copy of the file lives there) and run it headless, with `folder` as the
    working directory so that the directory pytest was started from is not a second search root."""
    cwd = os.getcwd()
    sys.path.insert(0, str(folder))
    os.chdir(folder)
    try:
        sys.modules.pop("bac_antenna_visualizer_demo", None)
        nb = importlib.import_module("bac_antenna_visualizer_demo")
        return nb.app.run()
    finally:
        os.chdir(cwd)
        sys.path.remove(str(folder))
        sys.modules.pop("bac_antenna_visualizer_demo", None)


def _constant(text: str, name: str) -> str:
    match = re.search(rf'^\s*{name} = "([^"]+)"', text, re.M)
    assert match is not None, f"{name} is not a string constant in the demo"
    return match.group(1)


_SYNTHETIC = {}


def _synthetic_run():
    """The demo run once on a synthetic pack folder beside a copy of the file; shared by the test classes."""
    if not _SYNTHETIC:
        tmp = Path(tempfile.mkdtemp())
        try:
            pack = build_synthetic_pack(tmp / "antenna")
            folder = tmp / "demo"
            folder.mkdir()
            shutil.copy(DEMO, folder / DEMO.name)
            shutil.copytree(pack, folder / "synthetic-2200")  # a pack folder beside the demo
            _, defs = _run_demo(folder)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        _SYNTHETIC.update(tmp=tmp, folder=folder, defs=defs)
    return _SYNTHETIC


class FileTests(unittest.TestCase):
    """The demo file by itself: no optimizer anywhere, the snapshot names the visualizer version it copies."""

    def test_no_optimizer_dependency(self):
        text = DEMO.read_text()
        self.assertNotIn("bac_antenna", text.replace("bac_antenna_visualizer", ""))
        self.assertNotIn("bac-antenna-optimizer", text.split("# ///")[1])  # the PEP 723 block
        self.assertNotIn("urllib", text)  # no sockets in WebAssembly
        self.assertNotIn("os.environ", text)  # no BAC_ANTENNA_PACKS on molab
        self.assertNotIn("tool.uv.sources", text)  # no path dependency in the PEP 723 block

    def test_snapshot_names_a_visualizer_version(self):
        demo_text, nb_text = DEMO.read_text(), NOTEBOOK.read_text()
        snap = _constant(demo_text, "TOOL_VERSION")
        self.assertRegex(snap, r"^\d+\.\d+\.\d+$")
        self.assertIn(f"| {snap} |", demo_text)  # the version is a row of the revision history it carries
        self.assertRegex(_constant(demo_text, "SNAPSHOT_DATE"), r"^\d{4}-\d{2}-\d{2}$")
        # the snapshot is of the current visualizer or of an earlier one, never of a later one
        self.assertLessEqual(
            tuple(int(x) for x in snap.split(".")),
            tuple(int(x) for x in _constant(nb_text, "TOOL_VERSION").split(".")),
        )


class SyntheticPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = _synthetic_run()
        cls.folder, cls.defs = run["folder"], run["defs"]

    def test_pack_found_beside_the_file(self):
        d = self.defs
        self.assertEqual(list(d["FOUND"]), ["synthetic-2200"])
        self.assertEqual(Path(d["pack_source"]).resolve(), (self.folder / "synthetic-2200").resolve())
        self.assertIn(self.folder.resolve(), [Path(r).resolve() for r in d["SEARCH_ROOTS"]])
        self.assertEqual(d["MODE"], "nominal")

    def test_nominal_geometry_is_the_stored_model(self):
        d = self.defs
        self.assertEqual(d["GEOMETRY"], d["PACK"]["models"][d["NOMINAL"]])
        self.assertTrue(d["GEOMETRY_NOTE"].startswith("Stored geometry of the nominal case"))
        self.assertTrue(any(p["prop"] == "patch" for p in d["GEOMETRY"]))

    def test_blend_endpoints_and_midpoint(self):
        d = self.defs
        models = d["PACK"]["models"]
        (_, c0), (_, c1) = d["axis_cases"]("gap")[:2]
        m0, m1 = models[c0], models[c1]
        self.assertEqual(d["blend_models"](m0, m1, 0.0), m0)
        self.assertEqual(d["blend_models"](m0, m1, 1.0), m1)
        mid = d["blend_models"](m0, m1, 0.5)
        top = next(i for i, p in enumerate(m0) if p["prop"] == "top_board")
        self.assertAlmostEqual(mid[top]["elevation"], (m0[top]["elevation"] + m1[top]["elevation"]) / 2)

    def test_blend_refuses_a_different_structure(self):
        d = self.defs
        m0 = d["PACK"]["models"][d["NOMINAL"]]
        self.assertIsNone(d["blend_models"](m0, m0[:-1], 0.5))
        other = [dict(p) for p in m0]
        other[0]["prop"] = "something_else"
        self.assertIsNone(d["blend_models"](m0, other, 0.5))

    def test_charts_and_tables_run(self):
        d = self.defs
        self.assertGreater(len(d["SENS"]), 0)
        self.assertEqual(len(d["SMITH_TABLE"]), 3)
        self.assertIn("demo snapshot", d["report_md"])
        self.assertIn(d["SNAPSHOT_DATE"], d["report_md"])


class StoredGeometryTests(unittest.TestCase):
    """The blend of two stored models equals the optimizer's live model between them (the tracked notebook's view)."""

    @classmethod
    def setUpClass(cls):
        cls.defs = _synthetic_run()["defs"]

    @staticmethod
    def _live(pack, values):
        from bac_antenna.antennas import get_antenna
        from bac_antenna.config import Config, apply_overrides, validate
        from bac_antenna.core import full_params

        raw = tomllib.loads(pack["config_text"])
        design = dict(pack["design"])
        # the gap axis' `also` override from visualizer_testkit's plan, which the pack does not carry; the stack
        # limit it lifts is the only check that depends on it, so applying it on every axis changes nothing else
        over = ["geometry.stack.max_height_mm=7.0"]
        for a in pack["meta"]["axes"]:
            if a.get("params"):
                for p in a["params"]:
                    design[p] = values[a["id"]]
            elif a.get("set"):
                over.append(f"{a['set']}={values[a['id']]:g}")
        cfg = Config(raw=apply_overrides(raw, over), source=Path("pack-config.toml"))
        validate(cfg)
        return get_antenna(cfg).model(full_params(design, cfg), cfg).primitives

    def test_blend_matches_live_model(self):
        d = self.defs
        pack = d["PACK"]
        models = pack["models"]
        nominal = {a["id"]: float(a["nominal"]) for a in pack["meta"]["axes"]}
        for a in pack["meta"]["axes"]:
            pts = d["axis_cases"](a["id"])
            for (l0, c0), (l1, c1) in zip(pts, pts[1:], strict=False):
                for w in (0.25, 0.5, 0.75):
                    blended = d["blend_models"](models[c0], models[c1], w)
                    live = self._live(pack, {**nominal, a["id"]: l0 + w * (l1 - l0)})
                    self.assertEqual(len(blended), len(live))
                    for p, q in zip(blended, live, strict=True):
                        self.assertEqual((p["kind"], p["prop"]), (q.kind, q.prop))
                        if p["kind"] in ("box", "cylinder"):
                            pairs = list(zip(p["start"] + p["stop"], list(q.start) + list(q.stop), strict=True))
                            if p.get("radius") is not None:
                                pairs.append((p["radius"], q.radius))
                        else:
                            pairs = [
                                (x, y)
                                for pp, qq in zip(p["points"], q.points, strict=True)
                                for x, y in zip(pp, qq, strict=True)
                            ]
                            pairs += [(p["elevation"], q.elevation), (p["length"] or 0.0, q.length or 0.0)]
                        for x, y in pairs:
                            self.assertAlmostEqual(x, y, places=9, msg=f"{a['id']} {c0}-{c1} w={w} {p['prop']}")


class RealPackTests(unittest.TestCase):
    """The demo on the pack zips beside it in the checkout; skipped when there are none."""

    @classmethod
    def setUpClass(cls):
        zips = sorted(DEMO.parent.glob("*.zip"))
        if not zips:
            raise unittest.SkipTest("no pack zip beside the demo")
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        shutil.copy(DEMO, cls.tmp / DEMO.name)
        for z in zips:
            shutil.copy(z, cls.tmp / z.name)
        cls.zips = zips
        _, cls.defs = _run_demo(cls.tmp)

    def test_every_zip_is_found_and_the_first_loads(self):
        d = self.defs
        names = []
        for z in self.zips:
            with zipfile.ZipFile(z) as zf:
                meta = next(n for n in zf.namelist() if n.endswith("pack.json"))
                names.append(json.loads(zf.read(meta))["name"])
        self.assertEqual(sorted(d["FOUND"]), sorted(names))
        self.assertEqual(d["MODE"], "nominal")
        self.assertGreater(len(d["PACK"]["sphere"]), 0)
        self.assertEqual(len(d["SMITH_TABLE"]), 3)
        self.assertEqual(len(d["GEOMETRY"]), len(d["PACK"]["models"][d["NOMINAL"]]))
        self.assertTrue(set(d["DEMO_PACKS"]) <= set(d["FOUND"]), "the snapshot cell names packs that are not here")

    def test_blend_of_outer_cases_reproduces_each_inner_case(self):
        """For every axis of every zip: blending the two outermost cases gives each inner case's stored model –
        the stored geometry is linear in the swept dimension, so the demo's blend is exact between any two cases."""
        d = self.defs
        for loc in d["FOUND"].values():
            pack = d["parse_pack"](d["read_location"](loc))
            models = pack["models"]
            for a in pack["meta"]["axes"]:
                pts = sorted((float(x["level"]), x["case"]) for x in a["levels"] if x["case"] in models)
                (l0, c0), (l1, c1) = pts[0], pts[-1]
                for level, case in pts[1:-1]:
                    blended = d["blend_models"](models[c0], models[c1], (level - l0) / (l1 - l0))
                    self.assertIsNotNone(blended, f"{pack['meta']['name']} {a['id']}")
                    for p, q in zip(blended, models[case], strict=True):
                        for key in ("start", "stop", "elevation", "length", "radius"):
                            if key in q and q[key] is not None:
                                self.assertTrue(
                                    np.allclose(p[key], q[key], atol=1e-9),
                                    f"{pack['meta']['name']} {a['id']} {case} {key}",
                                )
                        if "points" in q:
                            self.assertTrue(
                                np.allclose(p["points"], q["points"], atol=1e-9), f"{a['id']} {case} points"
                            )


def tearDownModule():
    if _SYNTHETIC:
        shutil.rmtree(_SYNTHETIC["tmp"], ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
