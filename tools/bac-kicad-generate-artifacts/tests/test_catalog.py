# SPDX-License-Identifier: MIT
"""The catalogs: values, packages and the resolution of a BOM line per grade."""

from __future__ import annotations

from pathlib import Path

import pytest
from bac_kicad_generate_artifacts.catalog import BomLine, load_catalog, package_of, parse_value, resolve
from genart_testkit import CATALOG

from bac_common.errors import ConfigError

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(CATALOG / "passives", CATALOG / "ics")


@pytest.mark.parametrize(
    ("text", "kind", "expected"),
    [
        ("4k7", "r", 4700.0),
        ("4.7k", "r", 4700.0),
        ("4,7k", "r", 4700.0),
        ("4k7F", "r", 4700.0),  # a stray unit letter is tolerated
        ("0R", "r", 0.0),
        ("60R4", "r", 60.4),
        ("100R", "r", 100.0),
        ("1M", "r", 1e6),
        ("20m", "r", 0.02),
        ("1.5kΩ", "r", 1500.0),
        ("100nF", "c", 1e-7),
        ("100 nF", "c", 1e-7),
        ("0.1u", "c", 1e-7),
        ("2u2", "c", 2.2e-6),
        ("4n7", "c", 4.7e-9),
        ("10uF", "c", 1e-5),
        ("100p", "c", 1e-10),
        ("R47", "r", 0.47),
    ],
)
def test_parse_value(text, kind, expected):
    assert parse_value(text, kind) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "4.7k7", "k", "Aratas D3SH-A1R1"])
def test_parse_value_rejects_non_values(text):
    assert parse_value(text, "r") is None


@pytest.mark.parametrize(
    ("footprint", "package"),
    [
        (R0603, "0603"),
        (C0402, "0402"),
        ("Capacitor_SMD:C_0201_0603Metric", "0201"),  # the imperial code wins over the metric one
        ("Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B", "1411"),
        ("Capacitor_Tantalum_SMD:CP_EIA-7343-31_Kemet-D", "2917"),
        ("bac:shunt-0612-4t", "0612"),
        ("Package_TO_SOT_SMD:SOT-23-8", ""),
        ("", ""),
    ],
)
def test_package_of(footprint, package):
    assert package_of(footprint) == package


def test_kind_from_the_first_reference():
    assert BomLine("R1, R2", 2, "", "", "").kind == "r"
    assert BomLine("C12", 1, "", "", "").kind == "c"
    assert BomLine("RN1", 1, "", "", "").kind == ""  # a network is not a resistor row
    assert BomLine("U1", 1, "", "", "").kind == ""


def test_example_catalog_loads(catalog):
    assert len(catalog.passives) == 15 and len(catalog.ics) == 14
    assert all(r["_value"] is not None for r in catalog.passives)
    assert catalog.ic_by_mpn("tcan334gdcnr")["id"] == "can-xcvr-sot23-8.tcan334g"


def test_passive_resolves_by_value_and_package_per_grade(catalog):
    line = BomLine("R1, R2", 2, "4k7", R0603, "")
    dev, flight = resolve(catalog, line, "dev"), resolve(catalog, line, "flight")
    assert dev.mpn == "RC0603FR-074K7L" and dev.lcsc and not dev.note
    assert flight.mpn == "TNPW06034K70FHEA" and flight.catalog_id == "r-4k7-0603-flight"
    assert resolve(catalog, BomLine("C1", 1, "100n", C0402, ""), "dev").catalog_id == "c-0.1u-0402-dev"


def test_passive_roles_and_statuses(catalog):
    jumper = resolve(catalog, BomLine("R3", 1, "0R", R0603, ""), "dev")
    assert jumper.row["role"] == "jumper" and not jumper.note
    shunt = resolve(catalog, BomLine("R9", 1, "50m", "bac:shunt-0306", ""), "dev")
    assert shunt.row["role"] == "shunt" and shunt.status == "sourcing-open" and shunt.note == ""
    conditional = resolve(catalog, BomLine("C2", 1, "10u", "Capacitor_SMD:C_0805_2012Metric", ""), "dev")
    assert conditional.status == "conditional" and conditional.note.startswith("X5R, 85 °C maximum")
    alternative = resolve(catalog, BomLine("C2", 1, "10u", "Capacitor_SMD:C_1210_3225Metric", ""), "flight")
    assert alternative.row["role"] == "alternative" and "alternative row" in alternative.note


def test_passive_without_a_row_says_why(catalog):
    missing = resolve(catalog, BomLine("R4", 1, "1k", R0603, ""), "dev")
    assert missing.row is None and missing.reason == "no dev row in the passives catalog"
    other = resolve(catalog, BomLine("R9", 1, "50m", "bac:shunt-0306", ""), "flight")
    assert other.reason == "no flight row (the other grade has one) in the passives catalog"
    assert "not a value" in resolve(catalog, BomLine("R5", 1, "DNI", R0603, ""), "dev").reason
    assert "no package code" in resolve(catalog, BomLine("R5", 1, "1k", "bac:custom", ""), "dev").reason


def test_passive_with_an_mpn_matches_it_first(catalog):
    line = BomLine("R1", 1, "4k7", R0603, "TNPW06034K70FHEA")
    assert resolve(catalog, line, "flight").catalog_id == "r-4k7-0603-flight"
    assert resolve(catalog, line, "dev").catalog_id == "r-4k7-0603-dev"  # the MPN is a flight row: value and package
    proposal = resolve(catalog, BomLine("C7", 1, "10p", C0402, "GCM1555C1H100FA16D"), "flight")
    assert proposal.row is None and "no flight row" in proposal.reason  # a proposal row is not released


def test_ic_dev_is_the_schematic_part(catalog):
    r = resolve(catalog, BomLine("U1", 1, "TCAN334G", "x", "TCAN334GDCNR"), "dev")
    assert r.mpn == "TCAN334GDCNR" and r.lcsc == "C191005" and not r.note
    alt = resolve(catalog, BomLine("U1", 1, "TCAN334", "x", "TCAN334DCNR"), "dev")
    assert alt.note == "alternative row"


def test_ic_flight_by_compatibility(catalog):
    drop_in = resolve(catalog, BomLine("U2", 1, "ESD751", "x", "ESD751DYAR"), "flight")
    assert drop_in.mpn == "ESD751DYARQ1" and not drop_in.note
    behavior = resolve(catalog, BomLine("U5", 1, "TLV75533P", "x", "TLV75533PDBVR"), "flight")
    assert behavior.mpn == "TLV73333PQDBVRQ1" and behavior.note.startswith("check: ")
    footprint = resolve(catalog, BomLine("U1", 1, "TCAN334G", "x", "TCAN334GDCNR"), "flight")
    assert footprint.mpn == "TCAN334GDCNR" and "TCAN3404DDFRQ1 needs a new footprint" in footprint.note
    qualified = resolve(catalog, BomLine("U3", 1, "RV-3032", "x", "RV-3032-C7-32.768KHZ-2.5PPM-TA-QA"), "flight")
    assert qualified.row["role"] == "reference" and qualified.note == "aec-q200 reference stays"
    none = resolve(catalog, BomLine("U4", 1, "STM32", "x", "STM32F405RGT7"), "flight")
    assert none.row is None and none.reason == "no flight candidate in slot mcu-lqfp64"
    # the catalog's rule 3: a qualified reference stays even when the slot has a flight row
    fram = resolve(catalog, BomLine("U6", 1, "FRAM", "x", "CY15B102Q-SXET"), "flight")
    assert (
        fram.mpn == "CY15B102Q-SXET" and fram.note == "aec-q100 reference stays (flight row CYEL15B102Q-SXM available)"
    )
    # a board that already carries the flight part keeps it, without the next-revision note
    fitted = resolve(catalog, BomLine("U1", 1, "TCAN3404", "x", "TCAN3404DDFRQ1"), "flight")
    assert fitted.mpn == "TCAN3404DDFRQ1" and fitted.note == ""
    assert resolve(catalog, BomLine("U1", 1, "TCAN3404", "x", "TCAN3404DDFRQ1"), "dev").note == "flight row"


def test_ic_lifecycle_and_verification_are_columns(catalog):
    old = BomLine("U7", 1, "MCP2517FD", "x", "MCP2517FDT-H/JHA")
    dev = resolve(catalog, old, "dev")
    assert dev.note == "alternative row" and dev.lifecycle == "nrnd" and dev.verified == "false"
    assert dev.flags == ["lifecycle", "unverified"] and dev.status == "active"
    assert resolve(catalog, old, "flight").note == "aec-q100 alternative stays"
    fresh = resolve(catalog, BomLine("U1", 1, "TCAN334G", "x", "TCAN334GDCNR"), "dev")
    assert fresh.flags == [] and fresh.lifecycle == "active" and fresh.verified == "true"
    passive = resolve(catalog, BomLine("R1", 1, "4k7", R0603, ""), "dev")
    assert passive.lifecycle == "" and passive.verified == "" and passive.flags == []


def test_ratings_come_from_the_row(catalog):
    r = resolve(catalog, BomLine("R1", 1, "4k7", R0603, ""), "flight")
    assert (r.tolerance, r.rating, r.dielectric, r.height) == ("1 %", "0.11 W", "", "")
    c = resolve(catalog, BomLine("C2", 1, "10u", "Capacitor_SMD:C_1210_3225Metric", ""), "flight")
    assert (c.tolerance, c.rating, c.dielectric) == ("10 %", "25 V", "X7R")
    u = resolve(catalog, BomLine("U1", 1, "x", "y", "TCAN334GDCNR"), "dev")
    assert (u.tolerance, u.rating, u.height) == ("", "-40 to 125 °C", "")
    none = resolve(catalog, BomLine("U9", 1, "x", "y", "NOPE"), "dev")
    assert (none.tolerance, none.rating, none.dielectric, none.height) == ("", "", "", "")


def test_obsolete_ic_is_refused(catalog):
    gone = BomLine("U8", 1, "STG3856", "x", "STG3856QTR")
    for grade in ("dev", "flight"):
        r = resolve(catalog, gone, grade)
        assert r.row is None and r.reason == "STG3856QTR is obsolete in the catalog" and r.status == "unresolved"


def test_lines_the_catalogs_do_not_cover(catalog):
    assert "not in the IC catalog" in resolve(catalog, BomLine("U9", 1, "x", "y", "NOPE123"), "dev").reason
    switch = resolve(catalog, BomLine("SW1", 1, "Aratas D3SH-A1R1", "bac:Aratas", ""), "dev")
    assert switch.reason == "no Manufacturer PN on the symbol, and not a resistor or capacitor"
    only_ics = load_catalog(None, CATALOG / "ics")
    assert resolve(only_ics, BomLine("R1", 1, "4k7", R0603, ""), "dev").reason == "no passives catalog configured"
    with pytest.raises(ValueError):
        resolve(catalog, BomLine("R1", 1, "4k7", R0603, ""), "proto")


def test_missing_files_and_columns_are_config_errors(tmp_path: Path):
    with pytest.raises(ConfigError, match="Passives catalog file missing"):
        load_catalog(tmp_path, None)
    with pytest.raises(ConfigError, match="IC catalog file missing"):
        load_catalog(None, tmp_path)
    (tmp_path / "bac-ics.csv").write_text("id,mpn\nx,y\n")
    with pytest.raises(ConfigError, match="lacks the column"):
        load_catalog(None, tmp_path)
    assert load_catalog(None, None).empty
