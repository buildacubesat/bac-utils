# SPDX-License-Identifier: MIT
"""The build BOMs: reading kicad-cli's export and writing the four files."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from bac_kicad_generate_artifacts import bom
from genart_testkit import CATALOG, RESOLVE_SAMPLE

from bac_common.catalog import load_catalog
from bac_common.errors import UsageError


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_read_export_groups_and_flags(tmp_path: Path):
    src = tmp_path / "bom-resolve.csv"
    src.write_text(RESOLVE_SAMPLE)
    lines = bom.read_export(src)
    assert len(lines) == 13
    assert lines[0].references == "R1, R2" and lines[0].quantity == 2 and lines[0].kind == "r"
    assert lines[5].references == "C3" and lines[5].dnp
    assert lines[6].mpn == "TCAN334GDCNR" and not lines[6].dnp
    pad = lines[12]
    assert pad.build == "dev" and pad.per_footprint == 4 and pad.quantity == 2 and not pad.fitted("flight")
    src.write_text('Reference,Qty,Value,Footprint,MPN,DNP\n,,,,,\n"R1, R2, R3",,1k,x,,\n')
    assert [line.quantity for line in bom.read_export(src)] == [3]  # a blank line is dropped, Qty counted
    src.write_text("Reference,Qty,Value,Footprint,MPN,DNP,Build,Qty per footprint\nJ4,1,x,y,,,proto,\n")
    with pytest.raises(UsageError, match="J4: Build is 'proto'"):
        bom.read_export(src)
    src.write_text('Reference,Qty,Value,Footprint,MPN,DNP,Build,Qty per footprint\n"J4, J5",2,x,y,,,,four\n')
    with pytest.raises(UsageError, match="J4: Qty per footprint is 'four', not a count"):
        bom.read_export(src)


def test_fold_per_footprint(tmp_path: Path):
    path = tmp_path / "bom.csv"
    fields = "Reference,${QUANTITY},Value,${DNP}"
    path.write_text(
        '"Reference","Qty","Value","DNP","Qty per footprint"\n"J401, J601","2","Pad","","4"\n"R1","1","4k7","",""\n'
    )
    assert bom.fold_per_footprint(path, fields) == 1
    assert path.read_text() == '"Reference","Qty","Value","DNP"\n"J401, J601","8","Pad",""\n"R1","1","4k7",""\n'
    assert bom.fold_per_footprint(path, fields) == 0  # the column is gone: nothing to fold
    path.write_text('"Reference","Value","Qty per footprint"\n"J1","x","3"\n')
    assert bom.fold_per_footprint(path, "Reference,Value") == 0  # no quantity column: the file is left as it is
    assert path.read_text() == '"Reference","Value","Qty per footprint"\n"J1","x","3"\n'
    assert bom.fold_per_footprint(path, "Reference,Value,") == 0  # a trailing comma in the field list is tolerated


def test_write_builds(tmp_path: Path):
    src = tmp_path / "bom-resolve.csv"
    src.write_text(RESOLVE_SAMPLE)
    catalog = load_catalog(CATALOG / "passives", CATALOG / "ics")
    build = {"dev": tmp_path / "bom-dev.csv", "flight": tmp_path / "bom-flight.csv"}
    summary = bom.write_builds(catalog, bom.read_export(src), build, tmp_path / "jlc.csv", tmp_path / "issues.csv")
    assert summary.lines == 13 and summary.resolved == {"dev": 9, "flight": 8} and summary.issues == 8
    assert summary.flagged == 0 and summary.not_fitted == {"dev": 0, "flight": 1}
    assert summary.note() == "9/13 dev, 8/12 flight resolved, 1 not fitted, 8 issues, 5 without LCSC"

    dev = _rows(build["dev"])
    assert list(dev[0]) == list(bom.BUILD_COLUMNS)
    r1 = dev[0]
    assert r1["Designator"] == "R1, R2" and r1["Qty"] == "2" and r1["Package"] == "0603"
    assert r1["Manufacturer PN"] == "RC0603FR-074K7L" and r1["LCSC"] == "C99782" and r1["Catalog"] == "r-4k7-0603-dev"
    r4 = dev[2]
    assert r4["Designator"] == "R4" and r4["Manufacturer PN"] == "" and r4["Status"] == "unresolved"
    assert r4["Note"].startswith("no dev row")
    c3 = dev[5]
    assert c3["DNP"] == "DNP" and c3["Status"] == "conditional" and c3["Note"].startswith("X5R")
    assert dev[6]["Lifecycle"] == "active" and dev[6]["Verified"] == "true" and r1["Lifecycle"] == ""
    assert (r1["Tolerance"], r1["Rating"], r1["Dielectric"], r1["Height"]) == ("1 %", "0.1 W", "", "")
    assert (c3["Tolerance"], c3["Rating"], c3["Dielectric"]) == ("10 %", "25 V", "X5R")
    assert dev[6]["Rating"] == "-40 to 125 °C" and dev[6]["Tolerance"] == ""
    sw1 = dev[10]
    assert sw1["Value"] == "Aratas D3SH-A1R1" and sw1["Note"].startswith("no Manufacturer PN")
    assert sw1["Rating"] == "" and sw1["Tolerance"] == ""
    assert dev[11]["Note"] == "DX07S016JA1R1500 is not in the IC catalog"  # no other-parts catalog loaded here
    pad = dev[12]
    assert pad["Designator"] == "J401, J601" and pad["Qty"] == "8" and pad["DNP"] == ""  # 2 footprints × 4 sockets

    flight = _rows(build["flight"])
    assert flight[0]["Manufacturer PN"] == "TNPW06034K70FHEA"
    assert flight[6]["Manufacturer PN"] == "TCAN334GDCNR" and "next board revision" in flight[6]["Note"]
    assert flight[7]["Manufacturer PN"] == "ESD751DYARQ1"
    assert flight[8]["Note"] == "aec-q200 reference stays"
    assert flight[9]["Status"] == "unresolved" and flight[9]["Note"] == "no flight candidate in slot mcu-lqfp64"
    pad = flight[12]
    assert pad["DNP"] == "DNP" and pad["Note"] == "dev build only – not fitted in flight"
    assert pad["Status"] == "unresolved" and pad["Manufacturer PN"] == "61300811821"  # not resolved for flight

    jlc = _rows(tmp_path / "jlc.csv")
    assert list(jlc[0]) == list(bom.JLCPCB_COLUMNS)
    assert [r["Designator"] for r in jlc] == [
        "R1,R2", "R3", "R4", "C1", "C2", "U1", "U2", "U3", "U4", "SW1", "J1", "J401,J601",
    ]  # fmt: skip
    assert jlc[0] == {
        "Comment": "4k7",
        "Designator": "R1,R2",
        "Footprint": "Resistor_SMD:R_0603_1608Metric",
        "LCSC Part #": "C99782",
    }
    assert jlc[5]["Comment"] == "TCAN334GDCNR" and jlc[9]["Comment"] == "Aratas D3SH-A1R1"

    issues = _rows(tmp_path / "issues.csv")
    assert list(issues[0]) == list(bom.ISSUE_COLUMNS)
    assert [(r["Designator"], r["Grade"], r["Kind"]) for r in issues] == [
        ("R4", "dev", "unresolved"),
        ("SW1", "dev", "unresolved"),
        ("J1", "dev", "unresolved"),
        ("J401, J601", "dev", "unresolved"),
        ("R4", "flight", "unresolved"),
        ("U4", "flight", "unresolved"),
        ("SW1", "flight", "unresolved"),
        ("J1", "flight", "unresolved"),
    ]  # the dev-only landing pad is no flight issue


def test_other_parts_resolve_like_ics(tmp_path: Path):
    src = tmp_path / "bom-resolve.csv"
    src.write_text(RESOLVE_SAMPLE)
    catalog = load_catalog(CATALOG / "passives", CATALOG / "ics", CATALOG / "other")
    build = {"dev": tmp_path / "bom-dev.csv", "flight": tmp_path / "bom-flight.csv"}
    summary = bom.write_builds(catalog, bom.read_export(src), build, tmp_path / "jlc.csv", tmp_path / "issues.csv")
    assert summary.note() == "11/13 dev, 9/12 flight resolved, 1 not fitted, 5 issues, 5 without LCSC"
    pad = _rows(build["dev"])[12]
    assert pad["Manufacturer PN"] == "61300811821" and pad["Manufacturer"] == "Würth Elektronik" and pad["Qty"] == "8"
    assert [r for r in _rows(tmp_path / "jlc.csv") if r["Designator"] == "J401,J601"][0]["LCSC Part #"] == ""
    flight = _rows(build["flight"])[12]
    assert flight["DNP"] == "DNP" and flight["Note"] == "dev build only – not fitted in flight"
    j1 = _rows(build["dev"])[11]
    assert j1["Manufacturer PN"] == "DX07S016JA1R1500" and j1["Manufacturer"] == "JAE"
    assert j1["Catalog"] == "conn-usb-c-16p.dx07s016ja1r1500" and j1["Verified"] == "true"
    flight = _rows(build["flight"])[11]
    assert flight["Manufacturer PN"] == "DX07S016JA1R1500" and flight["Note"] == "accepted reference stays"
    issues = _rows(tmp_path / "issues.csv")
    assert [r for r in issues if r["Designator"] == "J1"] == []  # accepted for flight, verified
    assert [r for r in issues if r["Designator"] == "SW1"][0]["Reason"].endswith("not a resistor or capacitor")


def test_flagged_rows_go_to_the_issues_list(tmp_path: Path):
    src = tmp_path / "bom-resolve.csv"
    src.write_text(
        "Reference,Qty,Value,Footprint,MPN,DNP\nU7,1,MCP2517FD,x,MCP2517FDT-H/JHA,\nU8,1,STG3856,x,STG3856QTR,\n"
    )
    catalog = load_catalog(None, CATALOG / "ics")
    build = {"dev": tmp_path / "bom-dev.csv"}
    summary = bom.write_builds(catalog, bom.read_export(src), build, tmp_path / "jlc.csv", tmp_path / "issues.csv")
    assert summary.note() == "1/2 dev resolved, 1 issue, 2 flagged, 2 without LCSC"
    dev = _rows(build["dev"])
    assert dev[0]["Lifecycle"] == "nrnd" and dev[0]["Verified"] == "false" and dev[0]["Note"] == "alternative row"
    assert dev[1]["Status"] == "unresolved" and dev[1]["Note"] == "STG3856QTR is obsolete in the catalog"
    issues = _rows(tmp_path / "issues.csv")
    assert [(r["Designator"], r["Kind"], r["Reason"]) for r in issues] == [
        ("U7", "lifecycle", "lifecycle nrnd"),
        ("U7", "unverified", "not confirmed against a datasheet"),
        ("U8", "unresolved", "STG3856QTR is obsolete in the catalog"),
    ]
