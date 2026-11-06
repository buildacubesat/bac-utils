# SPDX-License-Identifier: MIT
"""The frozen project: the copy, the fields written, the DNP attribute, the title blocks, FROZEN.md."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from bac_kicad_generate_artifacts import cli
from bac_kicad_generate_artifacts.freeze import freeze_project, target_dir
from genart_testkit import CATALOG, SYNTH

from bac_common import sexp
from bac_common.catalog import BomLine, load_catalog, resolve
from bac_common.errors import ExternalToolError
from bac_common.testing import invoke

LINES = [
    BomLine("R1, R2", 2, "4k7", "Resistor_SMD:R_0603_1608Metric", ""),
    BomLine("U1", 1, "TI TCAN334G", "Package_TO_SOT_SMD:SOT-23-8", "TCAN334GDCNR"),
    BomLine("J401", 1, "Landing pad", "bac:EPS-Module-Landing-Pad", "61300811821", build="dev", per_footprint=4),
    BomLine("U9", 1, "ghost", "x", "NOPE"),  # in no catalog, on no sheet
]
FLIGHT_ONLY_R2 = BomLine("R2", 1, "4k7", "Resistor_SMD:R_0603_1608Metric", "", build="flight")


def _props(node: sexp.Node) -> dict[str, str]:
    return {p.value(1): p.value(2) for p in node.children("property")}


def _symbols(path: Path) -> dict[str, sexp.Node]:
    _, root = sexp.parse_file(path)
    return {_props(n)["Reference"]: n for n in root.children("symbol")}


def _footprints(path: Path) -> dict[str, sexp.Node]:
    _, root = sexp.parse_file(path)
    return {_props(n)["Reference"]: n for n in root.children("footprint")}


@pytest.fixture
def catalog():
    return load_catalog(CATALOG / "passives", CATALOG / "ics", CATALOG / "other")


def _freeze(synth: Path, catalog, build: str):
    resolved = [resolve(catalog, line, build) for line in LINES]
    target = target_dir(synth, "bac-synth-v2", build)
    frozen = freeze_project(
        synth, target, build=build, resolved=resolved, catalog=catalog, commit="abc1234", tool="t 0.8.0",
        today=dt.date(2026, 11, 5),
    )  # fmt: skip
    return target, frozen


def test_target_is_a_sibling_of_the_project_folder(synth: Path):
    assert target_dir(synth, "bac-synth-v2", "flight") == synth.parent / "bac-synth-v2-frozen-flight"


def test_flight_freeze_writes_the_fields_and_the_dnp(synth: Path, catalog):
    target, frozen = _freeze(synth, catalog, "flight")
    assert target.is_dir() and not (target / "fp-info-cache").exists()
    assert sorted(p.name for p in target.iterdir()) == [
        "FROZEN.md", "bac-synth-v2.kicad_pcb", "bac-synth-v2.kicad_pro", "bac-synth-v2.kicad_sch", "power.kicad_sch",
    ]  # fmt: skip
    assert frozen.symbols == 3 and frozen.footprints == 3 and frozen.excluded == ["J401"]
    assert frozen.without_titleblock == []
    assert frozen.unresolved == [("U9", "NOPE is not in the IC or other-parts catalog")]
    assert frozen.note() == "3 symbols, 3 footprints, 1 DNP by Build, 1 unresolved"
    assert frozen.titleblocks == 3 and frozen.unplaced == []

    symbols = _symbols(target / "power.kicad_sch")
    r1 = _props(symbols["R1"])
    assert (r1["Manufacturer PN"], r1["LCSC"], r1["Digikey"]) == ("TNPW06034K70FHEA", "C2131944", "TNPW06034K70FHEA-ND")
    assert r1["Value"] == "4k7"  # untouched
    assert _props(symbols["U1"])["Manufacturer PN"] == "TCAN334GDCNR"  # footprint-only flight row: the reference stays
    assert symbols["J401"].child("dnp").value(1) == "yes" and symbols["R1"].child("dnp").value(1) == "no"
    j401 = _props(symbols["J401"])
    assert j401["Manufacturer PN"] == "61300811821" and "LCSC" not in j401 and j401["Build"] == "dev"  # not in flight
    # the new properties sit after the last one, hidden, at the Value's position
    lcsc = next(p for p in symbols["R1"].children("property") if p.value(1) == "LCSC")
    assert lcsc.child("hide").value(1) == "yes" and lcsc.child("at").value(1) == "0"
    keys = [p.value(1) for p in symbols["R1"].children("property")]
    assert keys[-2:] == ["LCSC", "Digikey"] and keys.index("Manufacturer PN") < keys.index("LCSC")

    footprints = _footprints(target / "bac-synth-v2.kicad_pcb")
    fr1 = _props(footprints["R1"])
    assert (fr1["Manufacturer PN"], fr1["LCSC"]) == ("TNPW06034K70FHEA", "C2131944") and fr1["Value"] == "100k"
    lcsc = next(p for p in footprints["R1"].children("property") if p.value(1) == "LCSC")
    assert lcsc.child("layer").value(1) == "F.Fab" and lcsc.child("hide").value(1) == "yes" and lcsc.child("uuid")
    attrs = {ref: [a.value for a in n.child("attr").atoms()[1:]] for ref, n in footprints.items()}
    assert attrs["J401"] == ["dnp"] and attrs["R1"] == ["smd"] and attrs["U1"] == ["smd"]

    for path in (target / "bac-synth-v2.kicad_sch", target / "power.kicad_sch", target / "bac-synth-v2.kicad_pcb"):
        _, root = sexp.parse_file(path)
        comments = [c.value(2) for c in root.child("title_block").children("comment")]
        numbers = [c.value(1) for c in root.child("title_block").children("comment")]
        assert len(set(numbers)) == len(numbers)  # into free slots, no number twice
        assert comments[-2:] == [
            "Frozen flight build 2026-11-05 (t 0.8.0)",
            "Catalogs unversioned; source abc1234",  # the fixture catalogs carry no README
        ]
    note = (target / "FROZEN.md").read_text()
    assert note.startswith("# Frozen flight build\n") and "| Source | `bac-synth-v2/kicad10/` at abc1234 |" in note
    assert "## Not fitted in flight (DNP by the Build field)\n\nJ401" in note and "| U9 | NOPE is not in" in note
    # the source project is untouched
    assert "LCSC" not in (synth / "power.kicad_sch").read_text()


def test_dev_freeze_keeps_the_dev_only_part_fitted_and_is_repeatable(synth: Path, catalog):
    target, frozen = _freeze(synth, catalog, "dev")
    assert frozen.excluded == [] and _symbols(target / "power.kicad_sch")["J401"].child("dnp").value(1) == "no"
    attrs = _footprints(target / "bac-synth-v2.kicad_pcb")["J401"].child("attr")
    assert attrs is None
    assert _props(_symbols(target / "power.kicad_sch")["R1"])["Manufacturer PN"] == "RC0603FR-074K7L"
    first = (target / "power.kicad_sch").read_bytes()
    target2, _ = _freeze(synth, catalog, "dev")  # a second run replaces the folder
    assert target2 == target and (target / "power.kicad_sch").read_bytes() == first
    (target / "~bac-synth-v2.kicad_pcb.lck").write_text("")
    with pytest.raises(ExternalToolError, match="is open in KiCad"):
        _freeze(synth, catalog, "dev")


def test_excluded_part_keeps_its_fields_and_the_attr_order(synth: Path, catalog):
    lines = [FLIGHT_ONLY_R2, LINES[1]]  # R2 flight only; U1 in both
    resolved = [resolve(catalog, line, "dev") for line in lines]
    target = target_dir(synth, "bac-synth-v2", "dev")
    pcb = synth / "bac-synth-v2.kicad_pcb"
    text = pcb.read_text()
    i = text.index('(property "Reference" "R2"')
    j = text.index("(attr smd)", i)
    pcb.write_text(text[:j] + "(attr smd allow_soldermask_bridges)" + text[j + len("(attr smd)") :])
    frozen = freeze_project(synth, target, build="dev", resolved=resolved, catalog=catalog, commit="x", tool="t")
    assert frozen.excluded == ["R2"] and frozen.unplaced == [] and frozen.symbols == 1
    r2 = _props(_symbols(target / "power.kicad_sch")["R2"])
    assert r2["Manufacturer PN"] == "" and "LCSC" not in r2  # untouched: not in this build
    assert _props(_symbols(target / "power.kicad_sch")["U1"])["LCSC"] == "C191005"
    attrs = [a.value for a in _footprints(target / "bac-synth-v2.kicad_pcb")["R2"].child("attr").atoms()[1:]]
    assert attrs == ["smd", "dnp", "allow_soldermask_bridges"]  # KiCad's own order


def test_board_attr_gains_dnp_and_title_block_without_free_slots_is_left_alone(synth: Path, catalog):
    pcb = synth / "bac-synth-v2.kicad_pcb"
    text = pcb.read_text()
    tb = text.index("(title_block")
    end = text.index("\n\t)", tb)
    _, root = sexp.parse_file(pcb)
    used = {c.value(1) for c in root.child("title_block").children("comment")}
    comments = "".join(f'\n\t\t(comment {n} "c{n}")' for n in range(1, 10) if str(n) not in used)
    pcb.write_text(text[:end] + comments + text[end:])
    target, frozen = _freeze(synth, catalog, "flight")
    assert frozen.titleblocks == 2 and frozen.without_titleblock == ["bac-synth-v2.kicad_pcb"]  # the two sheets
    assert "## Title blocks without the two comment lines" in (target / "FROZEN.md").read_text()
    _, root = sexp.parse_file(target / "bac-synth-v2.kicad_pcb")
    assert len(root.child("title_block").children("comment")) == 9
    assert [a.value for a in _footprints(target / "bac-synth-v2.kicad_pcb")["J401"].child("attr").atoms()[1:]] == [
        "dnp"
    ]


def test_freeze_stage_through_the_cli(fake, synth, tmp_path):
    cfg = tmp_path / "ga.toml"
    cfg.write_text(
        f'[catalog]\npassives = "{CATALOG / "passives"}"\nics = "{CATALOG / "ics"}"\nother = "{CATALOG / "other"}"\n'
    )
    args = ["--config", str(cfg), "--desktop", str(tmp_path / "o"), "--only", "freeze", str(synth)]
    r = invoke(cli._main, ["--freeze", "flight", "--dry-run", *args])
    assert r.exit_code == 0, r.output
    assert "· Freeze → bac-synth-v2-frozen-flight/ (flight build)" in r.stdout
    assert not (synth.parent / "bac-synth-v2-frozen-flight").exists()
    r = invoke(cli._main, ["--freeze", "flight", *args])
    assert r.exit_code == 0, r.output
    assert "✓ Freeze → bac-synth-v2-frozen-flight/ (" in r.stdout and "DNP by Build" in r.stdout
    target = synth.parent / "bac-synth-v2-frozen-flight"
    assert (target / "FROZEN.md").is_file() and "| Build | flight |" in (target / "FROZEN.md").read_text()
    assert _symbols(target / "power.kicad_sch")["J401"].child("dnp").value(1) == "yes"
    exports = [c for c in fake.commands if c[1:4] == ["sch", "export", "bom"]]
    assert len(exports) == 2 and exports[1][exports[1].index("--output") + 1].endswith("bom-freeze.csv")
    # without the catalogs the run refuses before the first project; a freeze outside the stage list is warned about
    r = invoke(cli._main, ["--freeze", "dev", "--desktop", str(tmp_path / "o"), "--only", "freeze", str(synth)])
    assert r.exit_code == 2 and "needs the part catalogs" in r.stderr
    r = invoke(cli._main, ["--freeze", "dev", "--config", str(cfg), "--dry-run", "--only", "bom", str(synth)])
    assert r.exit_code == 0 and "freeze stage is not in this run's stages" in r.stdout
    assert "Freeze" not in r.stdout.split("stages")[1]
    # a frozen folder is not a source
    frozen = synth.parent / "bac-synth-v2-frozen-flight"
    r = invoke(cli._main, ["--freeze", "flight", "--config", str(cfg), "--only", "freeze", str(frozen)])
    assert r.exit_code == 1 and "is a frozen folder itself" in r.stdout and frozen.is_dir()
    # --freeze without --only adds the stage to the run
    r = invoke(
        cli._main, ["--freeze", "dev", "--config", str(cfg), "--dry-run", "--desktop", str(tmp_path / "o"), str(synth)]
    )
    assert r.exit_code == 0 and "· Freeze → bac-synth-v2-frozen-dev/ (dev build)" in r.stdout and "· Zip" in r.stdout


def test_the_example_catalogs_resolve_the_synth_lines(catalog):
    assert resolve(catalog, LINES[2], "dev").lcsc == "" and resolve(catalog, LINES[2], "flight").row is None
    assert SYNTH.is_dir()
