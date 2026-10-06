# SPDX-License-Identifier: MIT
"""The pure functions: version tags, title blocks, layers, names and the export rename pass."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from bac_kicad_generate_artifacts.project import (
    ProjectError,
    apply_patch_rev,
    asset_prefix,
    board_name,
    copper_layers,
    detect_subsystem,
    discover,
    extract_v_from_title,
    layer_file_tokens,
    make_plan,
    make_vr_tag,
    normalize_export_names,
    normalize_r,
    read_titleblock,
    rewrite_gbrjob,
)
from genart_testkit import DSW, PANEL, SYNTH

from bac_common import sexp


class TestExtractVFromTitle:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("EPS Board v1", "v1"),
            ("EPS Board v1.2", "v1.2"),
            ("EPS Board v1.2.3", "v1.2.3"),
            ("EPS Board V2", "v2"),
            ("EPS Board v 3", "v3"),
            ("EPS Board", None),
            ("", None),
            ("Build a CubeSat v1 EPS Board", "v1"),
            ("Project overview", None),
        ],
    )
    def test_cases(self, title, expected):
        assert extract_v_from_title(title) == expected


class TestNormalizeR:
    @pytest.mark.parametrize(
        ("rev", "expected"),
        [
            ("1", "r1"),
            ("01", "r1"),
            ("r1", "r1"),
            ("R2", "r2"),
            ("r 3", "r3"),
            ("  r1  ", "r1"),
            ("rev-A", "r-rev-A"),
            ("!!!", "r-unknown"),
            ("", "r-unknown"),
        ],
    )
    def test_cases(self, rev, expected):
        assert normalize_r(rev) == expected


class TestMakeVrTag:
    def test_both(self):
        assert make_vr_tag("Board v1", "2") == "v1r2"

    def test_only_v(self):
        assert make_vr_tag("Board v1", None) == "v1"

    def test_only_r(self):
        assert make_vr_tag(None, "2") == "r2"

    def test_neither(self):
        assert make_vr_tag(None, None) == "v-unknownr-unknown"
        assert make_vr_tag("", "") == "v-unknownr-unknown"


class TestApplyPatchRev:
    def test_cases(self):
        assert apply_patch_rev("v1r2", None) == "v1r2"
        assert apply_patch_rev("v1r2", 1) == "v1r2.1"
        assert apply_patch_rev("v1r2", 0) == "v1r2.0"


def _root(text: str) -> sexp.Node:
    return sexp.parse(textwrap.dedent(text))


class TestLayers:
    def test_default_named_4_layer(self):
        root = _root("""\
            (kicad_pcb (version 20240108) (generator pcbnew)
              (layers
                (0 "F.Cu" signal)
                (1 "In1.Cu" signal)
                (2 "In2.Cu" signal)
                (31 "B.Cu" signal)
                (32 "B.Adhes" user "B.Adhesive")
                (44 "Edge.Cuts" user)
                (60 "User.1" user)
              )
            )
        """)
        assert copper_layers(root) == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

    def test_renamed_layers_keep_canonical_names(self):
        root = _root("""\
            (kicad_pcb
              (layers
                (0 "F.Cu" signal "F.Cu-SIG")
                (1 "In1.Cu" power "In1.Cu-GND")
                (2 "In2.Cu" power "In2.Cu-PWR")
                (31 "B.Cu" mixed "B.Cu MIX")
                (36 "B.SilkS" user "B.Silkscreen")
                (60 "User.1" user)
              )
            )
        """)
        assert copper_layers(root) == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        tokens = layer_file_tokens(root)
        assert tokens["F_Cu-SIG"] == "F_Cu" and tokens["B_Cu MIX"] == "B_Cu" and tokens["In1_Cu-GND"] == "In1_Cu"
        assert tokens["B_SilkS"] == "B_Silkscreen" and tokens["B_Silkscreen"] == "B_Silkscreen"
        assert tokens["User_1"] == "User_1"

    def test_jumper_and_user_layers(self):
        root = _root("""\
            (kicad_pcb
              (layers
                (0 "F.Cu" signal)
                (1 "In1.Cu" jumper)
                (31 "B.Cu" signal)
                (36 "F.Paste" user)
                (60 "User.1" user)
              )
            )
        """)
        assert copper_layers(root) == ["F.Cu", "In1.Cu", "B.Cu"]

    def test_no_layers_block_falls_back(self):
        assert copper_layers(_root("(kicad_pcb (version 20240108))")) == ["F.Cu", "B.Cu"]
        assert layer_file_tokens(_root("(kicad_pcb)")) == {}


class TestReadTitleblock:
    def test_full(self, tmp_path: Path):
        f = tmp_path / "x.kicad_pcb"
        f.write_text(
            '(kicad_pcb\n  (title_block\n    (title "EPS Board v2")\n    (date "2026-10-06")\n    (rev "1")\n    (company "BAC")\n    (comment 1 "Mänu")\n    (comment 4 "https://bac.page/x")\n  )\n)\n'
        )
        tb = read_titleblock(f)
        assert (tb.title, tb.rev, tb.date, tb.company) == ("EPS Board v2", "1", "2026-10-06", "BAC")
        assert tb.comments == {1: "Mänu", 4: "https://bac.page/x"}
        assert tb.variables()["COMMENT4"] == "https://bac.page/x" and tb.variables()["REVISION"] == "1"

    def test_empty_strings_become_none(self, tmp_path: Path):
        f = tmp_path / "x.kicad_pcb"
        f.write_text('(kicad_pcb (title_block (title "") (rev "")))')
        tb = read_titleblock(f)
        assert tb.title is None and tb.rev is None

    def test_no_titleblock(self, tmp_path: Path):
        f = tmp_path / "x.kicad_pcb"
        f.write_text("(kicad_pcb)")
        assert read_titleblock(f).title is None


class TestNames:
    def test_subsystem_from_path(self):
        assert (
            detect_subsystem(Path("/h/bac/bac-hardware/inhibit/deployment-switch/kicad10"), "bac-hardware") == "inhibit"
        )
        assert detect_subsystem(Path("/h/other/project/kicad10"), "bac-hardware") is None
        assert detect_subsystem(Path("/h/bac-hardware"), "bac-hardware") is None

    @pytest.mark.parametrize(
        ("pro", "pcb", "title", "subsystem", "expected"),
        [
            (
                "bac-deployment-switch-v1",
                "bac-deployment-switch-v1",
                "bac Deployment Switch v1",
                "inhibit",
                "deployment-switch",
            ),
            ("bac-rf-antenna-x-v1", "bac-rf-antenna-x-v1", None, "rf", "antenna-x"),  # no doubled prefix
            ("bac-magnetorquer-placeholder-xy-1U-v1", "x", None, "adcs", "magnetorquer-placeholder-xy-1U"),
            ("buck-v2.1", "buck-v2.1", None, "eps", "buck"),
            (None, "board", "bac EPS Buck Module v2", "eps", "board"),  # the board stem comes first
            (None, "v1", "bac eps Buck Module v2", "eps", "buck-module"),  # a stem that is only a version: title
            (None, "v1", "BAC Buck Module v2", None, "buck-module"),
            (None, "v1", None, "eps", "buck"),  # folder as the last resort
        ],
    )
    def test_board_name(self, pro, pcb, title, subsystem, expected):
        assert board_name(Path("/x/eps/buck/kicad10"), pro, pcb, title, "bac", subsystem) == expected

    def test_asset_prefix(self):
        assert asset_prefix("bac", "inhibit", "deployment-switch") == "bac-inhibit-"
        assert asset_prefix("bac", None, "deployment-switch") == "bac-"
        assert asset_prefix("bac", "eps", "eps") == "bac-"  # the project folder is the subsystem itself


class TestNormalizeExportNames:
    TOKENS = {
        "F_Cu": "F_Cu",
        "F_Cu MIX": "F_Cu",
        "B_Cu": "B_Cu",
        "In1_Cu GND": "In1_Cu",
        "F_SilkS": "F_Silkscreen",
        "F_Silkscreen": "F_Silkscreen",
    }

    def test_renames_to_the_scheme(self, tmp_path: Path):
        for n in (
            "board-v1-F_Cu.gbr",
            "board-v1-B_Cu.gbr",
            "board-v1-F_Silkscreen.gbr",
            "board-v1-Edge_Cuts.gbr",
            "board-v1-job.gbrjob",
        ):
            (tmp_path / n).write_text("x")
        renamed = normalize_export_names(tmp_path, ["board-v1"], "bac-eps-board-v1r2", self.TOKENS)
        assert len(renamed) == 5
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "bac-eps-board-v1r2-B_Cu.gbr",
            "bac-eps-board-v1r2-Edge_Cuts.gbr",
            "bac-eps-board-v1r2-F_Cu.gbr",
            "bac-eps-board-v1r2-F_Silkscreen.gbr",
            "bac-eps-board-v1r2-job.gbrjob",
        ]

    def test_display_names_and_spaces(self, tmp_path: Path):
        (tmp_path / "board-v1-F_Cu MIX.gbr").write_text("x")
        (tmp_path / "board-v1-In1_Cu GND.gbr").write_text("x")
        (tmp_path / "board-v1-User_9 notes.gbr").write_text("x")
        normalize_export_names(tmp_path, ["board-v1"], "t", self.TOKENS)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["t-F_Cu.gbr", "t-In1_Cu.gbr", "t-User_9_notes.gbr"]

    def test_stem_is_removed_from_the_front_only(self, tmp_path: Path):
        # the old substring replace turned "...-B_Cu" into "...-B_" for a project called "Cu"
        (tmp_path / "Cu-v1-B_Cu.gbr").write_text("x")
        normalize_export_names(tmp_path, ["Cu-v1", "Cu"], "t", {})
        assert [p.name for p in tmp_path.iterdir()] == ["t-B_Cu.gbr"]

    def test_drill_names(self, tmp_path: Path):
        for n in ("board-v1.drl", "board-v1-PTH.drl", "board-v1-NPTH.drl"):
            (tmp_path / n).write_text("x")
        normalize_export_names(tmp_path, ["board-v1"], "t", {})
        assert sorted(p.name for p in tmp_path.iterdir()) == ["t-NPTH.drl", "t-PTH.drl", "t.drl"]

    def test_collisions_count_up(self, tmp_path: Path):
        for n in ("a-v1-F_Cu.gbr", "b-v1-F_Cu.gbr", "c-v1-F_Cu.gbr"):
            (tmp_path / n).write_text("x")
        normalize_export_names(tmp_path, ["a-v1", "b-v1", "c-v1"], "t", {})
        assert sorted(p.name for p in tmp_path.iterdir()) == ["t-F_Cu-2.gbr", "t-F_Cu-3.gbr", "t-F_Cu.gbr"]

    def test_already_named_files_are_left(self, tmp_path: Path):
        (tmp_path / "t-F_Cu.gbr").write_text("x")
        assert normalize_export_names(tmp_path, ["t"], "t", {}) == {}

    def test_missing_folder(self, tmp_path: Path):
        assert normalize_export_names(tmp_path / "nope", ["x"], "t", {}) == {}

    def test_gbrjob_paths_follow(self, tmp_path: Path):
        job = {
            "Header": {},
            "FilesAttributes": [
                {"Path": "board-v1-F_Cu.gbr", "FileFunction": "Copper,L1,Top"},
                {"Path": "board-v1-B_Cu.gbr"},
            ],
        }
        (tmp_path / "board-v1-job.gbrjob").write_text(json.dumps(job))
        (tmp_path / "board-v1-F_Cu.gbr").write_text("x")
        (tmp_path / "board-v1-B_Cu.gbr").write_text("x")
        renamed = normalize_export_names(tmp_path, ["board-v1"], "t", {})
        assert rewrite_gbrjob(tmp_path, renamed) == 2
        data = json.loads((tmp_path / "t-job.gbrjob").read_text())
        assert [f["Path"] for f in data["FilesAttributes"]] == ["t-F_Cu.gbr", "t-B_Cu.gbr"]
        assert data["FilesAttributes"][0]["FileFunction"] == "Copper,L1,Top"


class TestDiscover:
    def test_synthetic_project(self):
        p = discover(SYNTH)
        assert p.pro_file is not None and p.pro_file.stem == "bac-synth-v2"
        assert p.sch_file is not None and p.sch_file.name == "bac-synth-v2.kicad_sch"  # not power.kicad_sch
        assert not p.panel and p.copper == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        assert p.pcb_title.title == "bac Synth Board v2" and p.pcb_title.rev == "3"

    def test_panel(self):
        p = discover(PANEL)
        assert p.panel and p.sch_file is None and p.sch_title.title is None

    def test_deployment_switch(self):
        p = discover(DSW)
        assert p.pcb_title.title == "bac Deployment Switch Aratas D3SH-A1R1 v1" and p.pcb_title.rev == "1"
        assert p.copper == ["F.Cu", "B.Cu"] and p.tokens["F_Cu MIX"] == "F_Cu"

    def test_errors(self, tmp_path: Path):
        with pytest.raises(ProjectError, match="Not a directory"):
            discover(tmp_path / "nope")
        with pytest.raises(ProjectError, match="No .kicad_pcb"):
            discover(tmp_path)
        (tmp_path / "a.kicad_pcb").write_text("(kicad_pcb)")
        (tmp_path / "b.kicad_pcb").write_text("(kicad_pcb)")
        with pytest.raises(ProjectError, match="Several .kicad_pcb"):
            discover(tmp_path)


class TestPlan:
    def test_paths(self, tmp_path: Path):
        plan = make_plan(discover(SYNTH), tmp_path, prefix="bac", hardware_root="fixtures")
        assert plan.base == "bac-eps-synth-v2r3"
        assert plan.out_dir == tmp_path / "synth-v2r3"
        assert plan.render_webp.name == "bac-eps-synth-v2r3-render.webp"
        assert plan.centroid_pos == tmp_path / "synth-v2r3" / "centroid" / "bac-eps-synth-v2r3-centroid.pos"
        assert plan.schematic_pdf.name == "bac-eps-synth-v2r3-schematic.pdf"
        assert plan.qr_board == tmp_path / "synth-v2r3" / ".work" / "project" / "bac-synth-v2.kicad_pcb"

    def test_patch_and_separate_schematic_tag(self, tmp_path: Path):
        plan = make_plan(discover(SYNTH), tmp_path, prefix="bac", hardware_root="none", pcb_patch=1, sch_patch=None)
        assert plan.pcb_tag == "v2r3.1" and plan.sch_tag == "v2r3"
        assert plan.base == "bac-synth-v2r3.1" and plan.bom_csv.name == "bac-synth-v2r3-bom.csv"

    def test_panel_uses_the_board_tag_everywhere(self, tmp_path: Path):
        plan = make_plan(discover(PANEL), tmp_path, prefix="bac", hardware_root="fixtures")
        assert plan.pcb_tag == plan.sch_tag == "v1r1" and plan.base == "bac-eps-synth-panel-v1r1"

    def test_deployment_switch_without_hardware_root(self, tmp_path: Path):
        plan = make_plan(discover(DSW), tmp_path, prefix="bac", hardware_root="bac-hardware")
        assert plan.base == "bac-deployment-switch-v1r1" and plan.out_dir.name == "deployment-switch-v1r1"
