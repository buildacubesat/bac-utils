# SPDX-License-Identifier: MIT
"""The build BOMs: reading kicad-cli's export and writing the four files."""

from __future__ import annotations

import csv
from pathlib import Path

from bac_kicad_generate_artifacts import bom
from bac_kicad_generate_artifacts.catalog import load_catalog
from genart_testkit import CATALOG, RESOLVE_SAMPLE


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_read_export_groups_and_flags(tmp_path: Path):
    src = tmp_path / "bom-resolve.csv"
    src.write_text(RESOLVE_SAMPLE)
    lines = bom.read_export(src)
    assert len(lines) == 12
    assert lines[0].references == "R1, R2" and lines[0].quantity == 2 and lines[0].kind == "r"
    assert lines[5].references == "C3" and lines[5].dnp
    assert lines[6].mpn == "TCAN334GDCNR" and not lines[6].dnp
    src.write_text('Reference,Qty,Value,Footprint,MPN,DNP\n,,,,,\n"R1, R2, R3",,1k,x,,\n')
    assert [line.quantity for line in bom.read_export(src)] == [3]  # a blank line is dropped, Qty counted


def test_write_builds(tmp_path: Path):
    src = tmp_path / "bom-resolve.csv"
    src.write_text(RESOLVE_SAMPLE)
    catalog = load_catalog(CATALOG / "passives", CATALOG / "ics")
    build = {"dev": tmp_path / "bom-dev.csv", "flight": tmp_path / "bom-flight.csv"}
    summary = bom.write_builds(catalog, bom.read_export(src), build, tmp_path / "jlc.csv", tmp_path / "issues.csv")
    assert summary.lines == 12 and summary.resolved == {"dev": 9, "flight": 8} and summary.issues == 7
    assert summary.flagged == 0
    assert summary.note() == "9/12 dev, 8/12 flight resolved, 7 issues, 4 without LCSC"

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
    assert dev[11]["Note"] == "DX07S016JA1R1500 is not in the IC catalog"  # no parts catalog loaded here

    flight = _rows(build["flight"])
    assert flight[0]["Manufacturer PN"] == "TNPW06034K70FHEA"
    assert flight[6]["Manufacturer PN"] == "TCAN334GDCNR" and "next board revision" in flight[6]["Note"]
    assert flight[7]["Manufacturer PN"] == "ESD751DYARQ1"
    assert flight[8]["Note"] == "aec-q200 reference stays"
    assert flight[9]["Status"] == "unresolved" and flight[9]["Note"] == "no flight candidate in slot mcu-lqfp64"

    jlc = _rows(tmp_path / "jlc.csv")
    assert list(jlc[0]) == list(bom.JLCPCB_COLUMNS)
    assert [r["Designator"] for r in jlc] == ["R1,R2", "R3", "R4", "C1", "C2", "U1", "U2", "U3", "U4", "SW1", "J1"]
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
        ("R4", "flight", "unresolved"),
        ("U4", "flight", "unresolved"),
        ("SW1", "flight", "unresolved"),
        ("J1", "flight", "unresolved"),
    ]


def test_parts_resolve_like_ics(tmp_path: Path):
    src = tmp_path / "bom-resolve.csv"
    src.write_text(RESOLVE_SAMPLE)
    catalog = load_catalog(CATALOG / "passives", CATALOG / "ics", CATALOG / "parts")
    build = {"dev": tmp_path / "bom-dev.csv", "flight": tmp_path / "bom-flight.csv"}
    summary = bom.write_builds(catalog, bom.read_export(src), build, tmp_path / "jlc.csv", tmp_path / "issues.csv")
    assert summary.note() == "10/12 dev, 9/12 flight resolved, 5 issues, 4 without LCSC"
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
