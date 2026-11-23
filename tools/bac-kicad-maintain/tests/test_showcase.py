# SPDX-License-Identifier: MIT
"""The catalog showcase projects on the catalog fixture and a small library."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from bac_kicad_maintain import cli
from bac_kicad_maintain import showcase as sc
from bac_kicad_maintain.audit import audit, load_repository
from bac_kicad_maintain.config import Settings, load_settings

from bac_common.catalog import load_catalog
from bac_common.errors import ConfigError, UsageError
from bac_common.sexp import parse
from bac_common.testing import HELP_MAX_LINES, invoke

FIXTURE = Path(__file__).resolve().parents[3] / "lib" / "bac-common" / "tests" / "catalog"
LIBRARY = "resources/kicad-libraries"
PRETTY = f"{LIBRARY}/footprints/bac.pretty"
SYMBOLS = f"{LIBRARY}/symbols/bac.kicad_sym"
FP_NICK = "bac KiCad Library Footprints v1"

README = """# {title}

## 1. Files

| File | Content |
| --- | --- |
| `x.csv` | rows |

## 2. How to use

Text.

## 8. Version history

| Version | Date | Change |
| --- | --- | --- |
| v0.9.1 | 2026-11-05 | newer |
| v0.9.0 | 2026-10-01 | older |
"""


def symbol(name: str, reference: str, footprint: str = "", mpn: str = "", pins: int = 2) -> str:
    """A KiCad-formatted library symbol made from the placeholder's text."""
    text = sc.PLACEHOLDER_SYMBOL.replace(sc.PLACEHOLDER, name)
    text = text.replace('(property "Reference" "X"', f'(property "Reference" "{reference}"')
    text = text.replace('(property "Footprint" ""', f'(property "Footprint" "{footprint}"')
    text = text.replace('(property "Manufacturer PN" ""', f'(property "Manufacturer PN" "{mpn}"')
    if pins == 4:
        extra = ""
        for number, x, angle in (("3", -6.35, 0), ("4", 6.35, 180)):
            extra += (
                f"\n\t\t\t(pin passive line\n\t\t\t\t(at {x} -1.27 {angle})\n\t\t\t\t(length 2.54)\n"
                f'\t\t\t\t(name "S{number}")\n\t\t\t\t(number "{number}")\n\t\t\t)'
            )
        marker = "\n\t\t)\n\t\t(embedded_fonts no)"
        text = text.replace(marker, extra + marker)
    return "\t" + text + "\n"


def two_units(name: str, mpn: str) -> str:
    """A symbol whose second unit is drawn 100 mm to the right of its origin, with a pin named like its number."""
    text = symbol(name, "J", mpn=mpn).rstrip("\n")
    unit2 = (
        f'\n\t\t(symbol "{name}_2_1"\n\t\t\t(rectangle\n\t\t\t\t(start 96.52 2.54)\n\t\t\t\t(end 104.14 -2.54)\n'
        "\t\t\t)\n"
        "\t\t\t(pin passive line\n\t\t\t\t(at 93.98 0 0)\n\t\t\t\t(length 2.54)\n"
        '\t\t\t\t(name "IO/3")\n\t\t\t\t(number "3")\n\t\t\t)\n'
        "\t\t\t(pin passive line\n\t\t\t\t(at 106.68 0 180)\n\t\t\t\t(length 2.54)\n"
        '\t\t\t\t(name "4")\n\t\t\t\t(number "4")\n\t\t\t)\n\t\t)'
    )
    marker = "\n\t\t(embedded_fonts no)"
    return text.replace(marker, unit2 + marker) + "\n"


def footprint(name: str, model: str | None = "${BAC_LIB_DIR}/3d/part.step", pads: int = 2, legacy: bool = False) -> str:
    out = [
        f'(footprint "{name}"',
        "\t(version 20260206)",
        '\t(generator "pcbnew")',
        '\t(generator_version "10.0")',
        '\t(layer "F.Cu")',
        f'\t(descr "{name}")',
        '\t(property "Reference" "REF**"\n\t\t(at 0 -2 0)\n\t\t(layer "F.SilkS")\n\t\t(uuid "aaaaaaaa-0000-4000-8000-000000000001")\n\t)',
        f'\t(property "Value" "{name}"\n\t\t(at 0 2 0)\n\t\t(layer "F.Fab")\n\t\t(uuid "aaaaaaaa-0000-4000-8000-000000000002")\n\t)',
        '\t(property "Datasheet" ""\n\t\t(at 0 0 0)\n\t\t(layer "F.Fab")\n\t\t(hide yes)\n\t)',
        '\t(property "Description" ""\n\t\t(at 0 0 0)\n\t\t(layer "F.Fab")\n\t\t(hide yes)\n\t)',
        "\t(attr smd)",
        "\t(fp_rect\n\t\t(start -2 -1)\n\t\t(end 2 1)\n\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n"
        '\t\t(fill no)\n\t\t(layer "F.CrtYd")\n\t\t(uuid "aaaaaaaa-0000-4000-8000-000000000003")\n\t)',
    ]
    for n in range(1, pads + 1):
        out.append(
            f'\t(pad "{n}" smd rect\n\t\t(at {n - 1.5} 0)\n\t\t(size 0.8 0.9)\n\t\t(layers "F.Cu" "F.Mask" "F.Paste")\n'
            f'\t\t(uuid "aaaaaaaa-0000-4000-8000-00000000001{n}")\n\t)'
        )
    if legacy:  # as KiCad 9 saved a footprint with a keepout
        out[1] = "\t(version 20241229)"
        out.append(
            '\t(zone\n\t\t(net 0)\n\t\t(net_name "")\n\t\t(layers "F.Cu")\n'
            '\t\t(uuid "aaaaaaaa-0000-4000-8000-0000000000ff")\n\t\t(keepout\n\t\t\t(tracks not_allowed)\n\t\t)\n'
            "\t\t(polygon\n\t\t\t(pts\n\t\t\t\t(xy -1 -1) (xy 1 -1) (xy 1 1)\n\t\t\t)\n\t\t)\n\t)"
        )
    out.append("\t(embedded_fonts no)")
    if model:
        out.append(f'\t(model "{model}"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)')
    return "\n".join(out) + "\n)\n"


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def make_root(tmp_path: Path, *, placeholder: bool = True) -> Path:
    root = tmp_path / "hw"
    for name in ("passives", "ics", "other"):
        shutil.copytree(FIXTURE / name, root / "resources" / "catalog" / name)
        write(root, f"resources/catalog/{name}/README.md", README.format(title=name))
    lib = f"{FP_NICK}:"
    symbols = [
        symbol("#unused ST STG3856QTR", "U", mpn="STG3856QTR"),
        symbol("Infineon CY15B102Q-SXET", "U", f"{lib}Infineon-CY15B102Q-SXET", "CY15B102Q-SXET"),
        symbol("TI ESD751", "D", "Diode_SMD:D_0603_1608Metric", "ESD751DYAR"),
        symbol("TI TCAN334", "U", "Package_TO_SOT_SMD:SOT-23-8", "tcan334gdcnr"),  # the case differs from the row's
        symbol("TI TMUX1309ABQBR", "U", f"{lib}TI-TMUX1309ABQBR", "TMUX1309ABQBR"),
        symbol("WE 150060WS75000", "D", f"{lib}WE-150060WS75000-LED-W", "150060WS75000"),
        symbol("WE Spacer A", "H", f"{lib}WE-9774025151R-SPACER-M2.5-2.5MM", "9774025151R"),
        symbol("WE Spacer B", "H", f"{lib}Spacer-B", "9774025151R"),  # one part number, two symbols
        two_units("Wide Connector", "MDT350M01001VT"),
        symbol("bac C", "C"),
        symbol("bac R", "R", f"{lib}R-0603"),
        symbol("bac R Shunt", "R", f"{lib}R-Shunt-0612-4T", pins=4),
    ]
    if placeholder:
        symbols.insert(6, "\t" + sc.PLACEHOLDER_SYMBOL + "\n")
    write(
        root,
        SYMBOLS,
        '(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n\t(generator_version "10.0")\n'
        + "".join(symbols)
        + ")\n",
    )
    for name in ("R-0603", "R-0402", "C-0402", "C-0805", "Infineon-CY15B102Q-SXET", "TI-TMUX1309ABQBR"):
        write(root, f"{PRETTY}/{name}.kicad_mod", footprint(name))
    connector = "bac-M.2-Key-M-bacBus-Connector"
    write(root, f"{PRETTY}/{connector}.kicad_mod", footprint(connector, pads=4, legacy=True))
    spacer = "WE-9774025151R-SPACER-M2.5-2.5MM"
    write(root, f"{PRETTY}/{spacer}.kicad_mod", footprint(spacer))
    write(root, f"{PRETTY}/R-Shunt-0306-4T.kicad_mod", footprint("R-Shunt-0306-4T", model=None, pads=4))
    write(
        root,
        f"{PRETTY}/WE-150060WS75000-LED-W.kicad_mod",
        footprint("WE-150060WS75000-LED-W", "${BAC_LIB_DIR}/3d/gone.step"),
    )
    write(root, f"{PRETTY}/#unused-C-1210.kicad_mod", footprint("#unused-C-1210"))
    write(root, f"{LIBRARY}/3d/part.step", "")
    stock = tmp_path / "stock"
    write(
        stock, "Package_TO_SOT_SMD.pretty/SOT-23-8.kicad_mod", footprint("SOT-23-8", "${KICAD10_3DMODEL_DIR}/x.step", 4)
    )
    write(stock, "Diode_SMD.pretty/D_SOD-523.kicad_mod", footprint("D_SOD-523", "${KICAD10_3DMODEL_DIR}/y.step"))
    write(stock, "Capacitor_SMD.pretty/C_1210_3225Metric.kicad_mod", footprint("C_1210_3225Metric", None))
    return root


def settings(tmp_path: Path) -> Settings:
    return replace(Settings(), showcase_kicad_footprints=str(tmp_path / "stock"))


def config(tmp_path: Path) -> Path:
    path = tmp_path / "maintain.toml"
    path.write_text(f'[showcase]\nkicad_footprints = "{tmp_path / "stock"}"\n', encoding="utf-8")
    return path


def call(tmp_path: Path, *args: str):
    return invoke(cli._main, ["--config", str(config(tmp_path)), *args])


def by_catalog(shows: list[sc.Showcase]) -> dict[str, sc.Showcase]:
    return {s.catalog: s for s in shows}


def kinds(show: sc.Showcase) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in show.findings:
        out.setdefault(f.kind, []).append(f.row)
    return out


def text_of(show: sc.Showcase, name: str) -> str:
    op = next(f for f in show.files if f.path.name == name)
    assert op.text is not None
    return op.text


def write_all(shows: list[sc.Showcase]) -> None:
    for show in shows:
        for op in show.pending:
            if op.state == "remove":
                op.path.unlink()
            else:
                op.path.parent.mkdir(parents=True, exist_ok=True)
                op.path.write_text(op.text, encoding="utf-8", newline="")


# ---------------------------------------------------------------------------
# What is placed, and how
# ---------------------------------------------------------------------------


def test_every_row_is_placed_once_and_every_file_parses(tmp_path):
    root = make_root(tmp_path)
    _, shows = sc.build(root, settings(tmp_path))
    folders = [root / "resources/catalog" / n for n in ("passives", "ics", "other")]
    catalog = load_catalog(*folders)
    rows = {"passives": catalog.passives, "ics": catalog.ics, "other": catalog.other}
    assert [s.catalog for s in shows] == ["passives", "ics", "other"]
    assert [s.counts["Catalog rows"] for s in shows] == [15, 15, 7]
    for show in shows:
        keys = [p.key for p in show.placements]
        assert len(keys) == len(set(keys)) and {p.id for p in show.placements} == {r["id"] for r in rows[show.catalog]}
        assert show.counts["Placed in the schematic"] == show.counts["Catalog rows"]
        references = [p.reference for p in show.placements]
        assert len(references) == len(set(references))
        assert show.folder == root / "resources/catalog" / show.catalog / "showcase"
        for op in show.files:
            if op.path.suffix in (".kicad_sch", ".kicad_pcb") or op.path.name.endswith("lib-table"):
                parse(op.text)
        project = json.loads(text_of(show, f"{show.project}.kicad_pro"))
        assert len(project["sheets"]) == len(show.sheets) + 1
        assert "not placed" not in kinds(show)


def test_passives_sections_symbols_and_footprints(tmp_path):
    lib, shows = sc.build(make_root(tmp_path), settings(tmp_path))
    show = by_catalog(shows)["passives"]
    assert [s.name for s in show.sheets] == ["Resistors Dev", "Resistors Flight", "Capacitors Dev", "Capacitors Flight"]
    assert [s.file for s in show.sheets][:2] == ["resistors-dev.kicad_sch", "resistors-flight.kicad_sch"]
    dev = show.sheets[0].items
    assert [p.id for p in dev] == ["r-0R-0603-dev", "r-50m-0306-dev", "r-4k7-0603-dev", "r-100k-0402-dev"]  # by value
    assert [p.reference for p in dev] == ["R1", "R2", "R3", "R4"]
    assert [p.symbol.name for p in dev] == ["bac R", "bac R Shunt", "bac R", "bac R"]
    assert [p.footprint for p in dev] == [f"{FP_NICK}:{n}" for n in ("R-0603", "R-Shunt-0306-4T", "R-0603", "R-0402")]
    assert all(p.mpn == "" and p.how == "passive" for p in dev)  # a passive stays thin: value and footprint
    found = kinds(show)
    assert found["no bac footprint"] == ["c-10u-1210-dev", "c-10u-1210-flight-x7r-std"]
    detail = next(f.detail for f in show.findings if f.row == "c-10u-1210-dev")
    assert "#unused-C-1210" in detail and "placed Capacitor_SMD:C_1210_3225Metric" in detail
    assert found["no 3D model"] == ["r-50m-0306-dev", "c-10u-1210-dev", "c-10u-1210-flight-x7r-std"]
    assert "stock footprint" not in found  # the fallback is reported once
    assert show.counts["On the board"] == 15
    sheet = text_of(show, "resistors-dev.kicad_sch")
    assert sheet.count("(lib_id ") == 4 and '(property "Value" "4k7"' in sheet
    assert '(symbol "bac Library Symbols v1:bac R"' in sheet and '(symbol "bac R_0_1"' in sheet  # the cache
    assert sheet.count("(no_connect") == 2 + 4 + 2 + 2


def test_parts_take_their_own_symbol_the_slot_symbol_or_the_placeholder(tmp_path):
    lib, shows = sc.build(make_root(tmp_path), settings(tmp_path))
    show = by_catalog(shows)["ics"]
    how = {p.id: (p.how, p.symbol.name) for p in show.placements}
    assert how["can-xcvr-sot23-8.tcan334g"] == ("own", "TI TCAN334")  # the part number matches whatever its case
    assert how["can-xcvr-sot23-8.tcan334"] == ("slot", "TI TCAN334")  # a drop-in under a reference with a symbol
    assert how["can-xcvr-sot23-8.tcan3404-q1"] == ("placeholder", sc.PLACEHOLDER)  # a different footprint
    assert how["esd-1ch-sod523.esd751-q1"] == ("slot", "TI ESD751")
    assert how["ldo-500ma-sot23-5.tlv73333p-q1"][0] == "placeholder"  # its reference has no symbol either
    assert how["mux-dual4-wqfn16.stg3856"][0] == "placeholder"
    found = kinds(show)
    assert "mux-dual4-wqfn16.stg3856" in found["symbol #unused"] and "mcu-lqfp64.stm32f405rgt7" in found["no symbol"]
    assert found["footprint differs"] == ["esd-1ch-sod523.esd751"]  # the row's footprint wins
    assert found["footprint from symbol"] == ["mux-dual4-wqfn16.tmux1309a"]
    assert (
        "can-xcvr-sot23-8.tcan3404-q1" in found["no footprint"] and "mcu-lqfp64.stm32f405rgt7" in found["no footprint"]
    )
    assert "ldo-500ma-sot23-5.tlv75533p" in found["footprint missing"]  # SOT-23-5 is not in the stock folder
    assert found["stock footprint"][0] == "can-xcvr-sot23-8.tcan334g"
    placements = {p.id: p for p in show.placements}
    assert placements["can-xcvr-sot23-8.tcan334"].mpn == "TCAN334DCNR"  # the row's part number in the instance
    assert placements["mux-dual4-wqfn16.tmux1309a"].footprint.endswith(":TI-TMUX1309ABQBR")
    assert placements["mcu-lqfp64.stm32f405rgt7"].value == "STM32F405RGT7"
    first = show.sheets[0].lines[0]
    assert first.label.startswith("can-xcvr-sot23-8 – ")
    assert [p.row["role"] for p in first.items] == ["reference", "alternative", "flight"]
    sheet = "".join(text_of(show, s.file) for s in show.sheets)
    assert '(property "Manufacturer PN" "TCAN334DCNR"' in sheet and "can-xcvr-sot23-8.tcan334\\nalternative" in sheet
    other = by_catalog(shows)["other"]
    assert kinds(other)["3D model missing"] == ["led-0603-white.150060ws75000"]
    assert other.counts["As placeholder"] == 4 and other.counts["Further symbols of a part number"] == 1


def test_the_board_carries_paths_references_and_unconnected_nets(tmp_path):
    lib, shows = sc.build(make_root(tmp_path), settings(tmp_path))
    show = by_catalog(shows)["passives"]
    board = parse(text_of(show, f"{show.project}.kicad_pcb"))
    footprints = board.children("footprint")
    assert len(footprints) == show.counts["On the board"] == 15
    sheets = {s.file: text_of(show, s.file) for s in show.sheets}
    uuids = set()
    for fp in footprints:
        path = fp.child("path").value(1)
        sheet_symbol, symbol_uuid = path.strip("/").split("/")
        sheet = next(s for s in show.sheets if s.symbol_uuid == sheet_symbol)
        assert f'(uuid "{symbol_uuid}")' in sheets[sheet.file]
        assert fp.child("sheetfile").value(1) == sheet.file and fp.child("sheetname").value(1) == f"/{sheet.name}/"
        assert fp.child("version") is None and fp.child("generator") is None and fp.child("at") is not None
        for node in fp.find_all("uuid"):
            assert node.value(1) not in uuids  # no identifier of the library file is repeated across placements
            uuids.add(node.value(1))
    shunt = next(fp for fp in footprints if fp.value(1).endswith(":R-Shunt-0306-4T"))
    nets = {pad.value(1): pad.child("net").value(1) for pad in shunt.children("pad")}
    assert nets == {
        "1": "unconnected-(R2-Pad1)",
        "2": "unconnected-(R2-Pad2)",
        "3": "unconnected-(R2-S3-Pad3)",
        "4": "unconnected-(R2-S4-Pad4)",
    }
    pad3 = next(p for p in shunt.children("pad") if p.value(1) == "3")
    assert pad3.child("pinfunction").value(1) == "S3_3" and pad3.child("pintype").value(1) == "passive+no_connect"
    properties = {p.value(1): p.value(2) for p in shunt.children("property")}
    assert properties["Reference"] == "R2" and properties["Value"] == "50m"
    assert board.child("title_block").child("company").value(1) == "nihil.space GmbH"
    assert len(board.children("gr_rect")) == 1 and len(board.children("gr_text")) == 4
    ics = by_catalog(shows)["ics"]
    ic_board = parse(text_of(ics, f"{ics.project}.kicad_pcb"))
    fram = next(fp for fp in ic_board.children("footprint") if fp.value(1).endswith(":Infineon-CY15B102Q-SXET"))
    assert {p.value(1): p.value(2) for p in fram.children("property")}["Manufacturer PN"] == "CY15B102Q-SXET"


def test_title_block_follows_the_catalog_readme(tmp_path):
    root = make_root(tmp_path)
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    show = shows[0]
    assert (show.version, show.date) == ("0.9.1", "2026-11-05")
    block = parse(text_of(show, "ics-01.kicad_sch")).child("title_block")
    values = {c.head: c.value(1) for c in block.children() if c.head != "comment"}
    assert values == {
        "title": "bac ICs Catalog Showcase",
        "date": "2026-11-05",
        "rev": "0.9.1",
        "company": "nihil.space GmbH",
    }
    assert block.child("comment").value(2) == sc.COMMENT
    assert "0.9.1, 2026-11-05" in text_of(show, sc.REPORT)
    (root / "resources/catalog/ics/README.md").write_text("# ICs\n", encoding="utf-8")
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    block = parse(text_of(shows[0], "ics-01.kicad_sch")).child("title_block")
    assert block.child("date") is None and block.child("rev") is None
    assert "no version history" in text_of(shows[0], sc.REPORT)


# ---------------------------------------------------------------------------
# Stability
# ---------------------------------------------------------------------------


def test_a_second_run_changes_nothing_and_a_new_row_keeps_the_others(tmp_path):
    root = make_root(tmp_path)
    _, shows = sc.build(root, settings(tmp_path))
    assert all(f.state in ("new", "changed") for s in shows for f in s.files)
    ics = by_catalog(shows)["ics"]
    first = "".join(text_of(ics, s.file) for s in ics.sheets)
    before = set(re.findall(r'\n\t\t\(uuid "([0-9a-f-]{36})"\)\n\t\t\(property "Reference"', first))
    assert len(before) == 15
    write_all(shows)
    _, again = sc.build(root, settings(tmp_path))
    assert {f.state for s in again for f in s.files} == {"unchanged"}
    pro = ics.folder / f"{ics.project}.kicad_pro"
    saved = json.loads(pro.read_text())
    saved["board"] = {}  # KiCad saved the project: its file is left alone from then on
    pro.write_text(json.dumps(saved))
    _, again = sc.build(root, settings(tmp_path), ["ics"])
    assert [f.path.name for f in again[0].files if f.state == "kept"] == [pro.name] and not again[0].pending
    csv = root / "resources/catalog/ics/bac-ics.csv"
    rows = csv.read_text(encoding="utf-8").splitlines()
    rows.append(
        rows[1]
        .replace("can-xcvr-sot23-8.tcan334g", "can-xcvr-sot23-8.new")
        .replace(",reference,reference,", ",alternative,drop-in,")
    )
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    _, third = sc.build(root, settings(tmp_path), ["ics"])
    sheet = "".join(text_of(third[0], s.file) for s in third[0].sheets)
    assert all(f'(uuid "{value}")' in sheet for value in before)
    assert "can-xcvr-sot23-8.new" in [p.id for p in third[0].placements]


def test_stale_generated_sheets_are_removed_and_other_sheets_left(tmp_path):
    root = make_root(tmp_path)
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    write_all(shows)
    folder = shows[0].folder
    write(folder, "ics-09.kicad_sch", f'(kicad_sch\n\t(version 1)\n\t(generator "{sc.GENERATOR}")\n)\n')
    write(folder, "notes.kicad_sch", '(kicad_sch\n\t(version 1)\n\t(generator "eeschema")\n)\n')
    _, again = sc.build(root, settings(tmp_path), ["ics"])
    assert [(f.path.name, f.state) for f in again[0].pending] == [("ics-09.kicad_sch", "remove")]


# ---------------------------------------------------------------------------
# README and the placeholder symbol
# ---------------------------------------------------------------------------


def test_the_readme_block_goes_under_files_and_is_refreshed_in_place(tmp_path):
    root = make_root(tmp_path)
    readme = root / "resources/catalog/ics/README.md"
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    text = text_of(shows[0], "README.md")
    block = text[text.index(sc.README_BEGIN) : text.index(sc.README_END)]
    assert text.index("## 1. Files") < text.index(sc.README_BEGIN) < text.index("## 2. How to use")
    assert (
        "**Showcase.**" in block
        and "showcase/bac-catalog-ics-showcase.kicad_pro" in block
        and "## Showcase" not in block
    )
    assert (
        text.replace(text[text.index(sc.README_BEGIN) : text.index(sc.README_END) + len(sc.README_END)] + "\n\n", "")
        == readme.read_text()
    )
    readme.write_text(text.replace("**Showcase.** ", "**Showcase.** stale "), encoding="utf-8")
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    assert text_of(shows[0], "README.md") == text
    readme.write_text(text, encoding="utf-8")
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    assert next(f for f in shows[0].files if f.path.name == "README.md").state == "unchanged"


def test_a_readme_without_files_gets_a_section_before_the_history(tmp_path):
    root = make_root(tmp_path)
    readme = root / "resources/catalog/other/README.md"
    readme.write_text(
        "# Other\n\nIntro.\n\n## Version history\n\n| Version | Date | Change |\n| --- | --- | --- |\n| 0.6.0 | 2026-11-11 | x |\n"
    )
    _, shows = sc.build(root, settings(tmp_path), ["other"])
    text = text_of(shows[0], "README.md")
    assert text.index("Intro.") < text.index("## Showcase") < text.index("## Version history")
    readme.write_text("# Other\n\nIntro.\n")
    _, shows = sc.build(root, settings(tmp_path), ["other"])
    assert text_of(shows[0], "README.md").endswith(sc.README_END + "\n")


def test_the_placeholder_symbol_is_added_in_name_order_once(tmp_path):
    root = make_root(tmp_path, placeholder=False)
    lib, shows = sc.build(root, settings(tmp_path), ["ics"])
    assert by_catalog(shows)["ics"].counts["As placeholder"] > 0  # the built-in copy serves the plan
    text = sc.ensure_placeholder(lib)
    names = [s.value(1) for s in parse(text).children("symbol")]
    assert names == sorted(names) and sc.PLACEHOLDER in names
    assert names.index(sc.PLACEHOLDER) == names.index("bac C") + 1
    (root / SYMBOLS).write_text(text, encoding="utf-8")
    lib, _ = sc.build(root, settings(tmp_path), ["ics"])
    assert sc.ensure_placeholder(lib) is None


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing_and_yes_writes_everything(tmp_path):
    root = make_root(tmp_path, placeholder=False)
    r = call(tmp_path, "showcase", str(root), "--dry-run")
    assert r.exit_code == 0 and "Files to write or remove" in r.stdout
    assert not (root / "resources/catalog/ics/showcase").exists() and sc.PLACEHOLDER not in (root / SYMBOLS).read_text()
    assert "no symbol" in r.stdout and "adds bac Catalog Placeholder" in r.stdout
    call(tmp_path, "showcase", str(root))  # no terminal to ask on: the answer is no
    assert not (root / "resources/catalog/ics/showcase").exists() and sc.PLACEHOLDER not in (root / SYMBOLS).read_text()
    r = call(tmp_path, "showcase", str(root), "--yes")
    assert r.exit_code == 0, r.stdout + r.stderr
    assert sc.PLACEHOLDER in (root / SYMBOLS).read_text() and (root / (SYMBOLS + ".bak")).is_file()
    for name in ("passives", "ics", "other"):
        folder = root / "resources/catalog" / name / "showcase"
        present = {p.name for p in folder.iterdir()}
        assert {f"bac-catalog-{name}-showcase.kicad_{s}" for s in ("pro", "sch", "pcb")} <= present
        assert {"sym-lib-table", "fp-lib-table", sc.REPORT} <= present and not any(n.endswith(".bak") for n in present)
        assert (folder.parent / "README.md.bak").is_file()
    r = call(tmp_path, "showcase", str(root), "--yes")
    assert r.exit_code == 0 and "nothing to write" in r.stdout


def test_json_one_catalog_and_usage_errors(tmp_path):
    root = make_root(tmp_path)
    r = call(tmp_path, "showcase", str(root), "--catalog", "ics", "--dry-run", "--json")
    data = json.loads(r.stdout)
    assert r.exit_code == 0 and data["command"] == "showcase" and data["dry_run"] is True
    assert [c["catalog"] for c in data["catalogs"]] == ["ics"]
    entry = data["catalogs"][0]
    assert entry["counts"]["Catalog rows"] == 15 and entry["catalog_version"] == "0.9.1"
    assert {f["kind"] for f in entry["findings"]} >= {"no symbol", "no footprint"}
    assert {f["state"] for f in entry["files"]} == {"new", "changed"}
    assert call(tmp_path, "showcase", str(root), "--json").exit_code == 2  # a report cannot ask
    assert call(tmp_path, "showcase", str(root), "--catalog", "nope").exit_code == 2
    assert call(tmp_path, "showcase", str(root / "missing")).exit_code == 2
    shutil.rmtree(root / "resources/catalog/other")
    assert call(tmp_path, "showcase", str(root), "--catalog", "other").exit_code == 2
    r = call(tmp_path, "showcase", str(root), "--catalog", "passives,ics", "--dry-run", "--json")
    assert [c["catalog"] for c in json.loads(r.stdout)["catalogs"]] == ["passives", "ics"]


def test_help_fits(tmp_path):
    r = call(tmp_path, "showcase", "--help")
    lines = r.stdout.rstrip("\n").splitlines()
    assert r.exit_code == 0 and len(lines) <= HELP_MAX_LINES and all(len(line) <= 80 for line in lines)
    for flag in ("--catalog", "--dry-run", "--yes", "--json", "--no-backup"):
        assert flag in r.stdout


def test_config_keys(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('[showcase]\nkicad_footprints = "/x"\nsymbol_library = "S"\nfootprint_library = "F"\n')
    loaded = load_settings(str(path))
    assert (loaded.showcase_kicad_footprints, loaded.showcase_symbol_library, loaded.showcase_footprint_library) == (
        "/x",
        "S",
        "F",
    )
    path.write_text('[showcase]\nsymbol_library = "a:b"\n')
    with pytest.raises(ConfigError):
        load_settings(str(path))
    path.write_text("[showcase]\nnope = 1\n")
    with pytest.raises(ConfigError):
        load_settings(str(path))
    with pytest.raises(UsageError):
        sc.build(tmp_path / "nowhere", Settings())


# ---------------------------------------------------------------------------
# The audit reads the projects
# ---------------------------------------------------------------------------


def test_the_audit_counts_showcase_placements(tmp_path):
    root = make_root(tmp_path)
    catalogs = [Path(f"resources/catalog/{n}") for n in ("passives", "ics", "other")]
    before = audit(load_repository(root, Path(LIBRARY), catalogs))
    unplaced = {f.subject for f in before.symbols if f.kind == "symbol not placed"}
    assert {"TI TCAN334", "bac R", "Infineon CY15B102Q-SXET"} <= unplaced  # a catalog row alone is no placement
    assert sc.PLACEHOLDER not in unplaced  # the showcase's stand-in is never reported
    assert call(tmp_path, "showcase", str(root), "--yes").exit_code == 0
    repo = load_repository(root, Path(LIBRARY), catalogs)
    after = audit(repo)
    assert after.counts["boards"] == 3 and after.counts["sheets"] == sum(1 for _ in root.rglob("showcase/*.kicad_sch"))
    assert not [f for f in after.symbols if f.kind == "symbol not placed"]
    assert not [f for f in after.libraries]
    # What the showcase cannot place stays a finding: a row's footprint the library lacks, a model that is gone.
    from_showcase = [f for f in after.broken_links if "showcase" in f.where]
    assert {f.kind for f in from_showcase} == {"sheet footprint", "board model"}
    assert [f.subject for f in from_showcase if f.kind == "board model"] == ["D1 ${BAC_LIB_DIR}/3d/gone.step"]
    used = {f.subject for f in after.unused_footprints}
    assert "R-0402" not in used and "R-Shunt-0306-4T" not in used  # placed by the passives showcase only


# ---------------------------------------------------------------------------
# Review findings of 2026-11-14
# ---------------------------------------------------------------------------


def test_a_further_unit_keeps_its_fields_and_names_its_nets_by_unit(tmp_path):
    lib, shows = sc.build(make_root(tmp_path), settings(tmp_path), ["other"])
    show = shows[0]
    wide = next(p for p in show.placements if p.symbol.name == "Wide Connector")
    assert sorted(wide.symbol.units) == [1, 2]
    origins = sc._unit_origins(wide)
    sheet = parse(text_of(show, next(s.file for s in show.sheets if wide in s.items)))
    instances = [s for s in sheet.children("symbol") if s.child("lib_id").value(1).endswith(":Wide Connector")]
    assert [s.child("unit").value(1) for s in instances] == ["1", "2"]
    flags = {tuple(float(a.value) for a in n.child("at").atoms()[1:3]) for n in sheet.children("no_connect")}
    for instance, unit in zip(instances, (1, 2), strict=True):
        x, y = origins[unit]
        box = wide.symbol.boxes[unit]
        reference = next(p for p in instance.children("property") if p.value(1) == "Reference")
        fx, fy = (float(a.value) for a in reference.child("at").atoms()[1:3])
        assert x + box[0] - 1 <= fx <= x + box[2] + 1 and wide.y <= fy <= wide.y + wide.height  # beside its own unit
        for pin in wide.symbol.units[unit]:
            assert (round(x + pin.x, 4), round(y + pin.y, 4)) in flags
    lib_y = 3.556  # the Reference field sits above the origin in the library: a smaller Y on the sheet
    reference = next(p for p in instances[0].children("property") if p.value(1) == "Reference")
    assert float(reference.child("at").atoms()[2].value) == pytest.approx(origins[1][1] - lib_y)
    nets = sc._pad_nets(wide)
    assert nets["1"][0] == f"unconnected-({wide.reference}-Pad1)"  # no name
    assert nets["3"][0] == f"unconnected-({wide.reference}B-IO{{slash}}3-Pad3)" and nets["3"][1] == "IO/3_3"
    assert nets["4"][0] == f"unconnected-({wide.reference}-Pad4)"  # a name equal to the number is no name


def test_every_symbol_of_a_part_number_is_placed(tmp_path):
    lib, shows = sc.build(make_root(tmp_path), settings(tmp_path), ["other"])
    show = shows[0]
    spacers = [p for p in show.placements if p.id == "spacer-m2.5-2.5mm.9774025151r"]
    assert [(p.symbol.name, p.how, p.key) for p in spacers] == [
        ("WE Spacer A", "own", "spacer-m2.5-2.5mm.9774025151r"),  # the one on the row's footprint
        ("WE Spacer B", "also", "spacer-m2.5-2.5mm.9774025151r#2"),
    ]
    assert spacers[1].footprint.endswith(":Spacer-B") and spacers[0].reference != spacers[1].reference
    assert kinds(show)["further symbol"] == ["spacer-m2.5-2.5mm.9774025151r"]


def test_a_footprint_zone_moves_with_its_footprint_and_loses_a_numbered_net(tmp_path):
    lib, shows = sc.build(make_root(tmp_path), settings(tmp_path), ["other"])
    board = parse(text_of(shows[0], f"{shows[0].project}.kicad_pcb"))
    fp = next(f for f in board.children("footprint") if f.value(1).endswith(":bac-M.2-Key-M-bacBus-Connector"))
    zone = fp.child("zone")
    assert zone is not None and zone.child("net") is None and zone.child("net_name") is None
    assert zone.child("keepout") is not None and fp.child("version") is None
    # The outline (-1,-1) (1,-1) (1,1) of the library file sits around the footprint's position on the board.
    x, y = (float(a.value) for a in fp.child("at").atoms()[1:3])
    outline = [tuple(float(a.value) for a in n.atoms()[1:3]) for n in zone.find_all("xy")]
    assert outline == [pytest.approx((x - 1, y - 1)), pytest.approx((x + 1, y - 1)), pytest.approx((x + 1, y + 1))]
    assert x > 20 and y > 20


def test_crlf_inputs_stay_consistent(tmp_path):
    root = make_root(tmp_path, placeholder=False)
    for rel in (SYMBOLS, "resources/catalog/ics/README.md"):
        path = root / rel
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    lib, shows = sc.build(root, settings(tmp_path), ["ics"])
    for op in shows[0].files:
        if op.path.suffix in (".kicad_sch", ".kicad_pcb"):
            assert "\r" not in op.text
    readme = text_of(shows[0], "README.md")
    assert readme.count("\r\n") == readme.count("\n") and sc.README_BEGIN in readme
    library = sc.ensure_placeholder(lib)
    assert library.count("\r\n") == library.count("\n")
    (root / SYMBOLS).write_bytes(library.encode())
    write_all(shows)
    _, again = sc.build(root, settings(tmp_path), ["ics"])
    assert not again[0].pending


def test_half_a_readme_block_and_a_fenced_heading(tmp_path):
    root = make_root(tmp_path)
    readme = root / "resources/catalog/ics/README.md"
    original = readme.read_text()
    readme.write_text(original + "\n" + sc.README_BEGIN + "\nleft over\n")
    with pytest.raises(sc.ShowcaseError):
        sc.build(root, settings(tmp_path), ["ics"])
    readme.write_text(original.replace("| `x.csv` | rows |", "| `x.csv` | rows |\n\n```\n## not a heading\n```"))
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    text = text_of(shows[0], "README.md")
    assert text.index("## not a heading") < text.index(sc.README_BEGIN) < text.index("## 2. How to use")


def test_passives_need_no_placeholder_and_a_locked_project_stops_the_run(tmp_path):
    root = make_root(tmp_path, placeholder=False)
    r = call(tmp_path, "showcase", str(root), "--catalog", "passives", "--yes")
    assert r.exit_code == 0 and sc.PLACEHOLDER not in (root / SYMBOLS).read_text()
    folder = root / "resources/catalog/passives/showcase"
    (folder / "resistors-dev.kicad_sch").write_text("edited\n")
    (folder / "~resistors-dev.kicad_sch.lck").write_text("")
    r = call(tmp_path, "showcase", str(root), "--catalog", "passives", "--yes")
    assert r.exit_code == 1 and "open" in r.stderr and (folder / "resistors-dev.kicad_sch").read_text() == "edited\n"
    (folder / "~resistors-dev.kicad_sch.lck").unlink()
    r = call(tmp_path, "showcase", str(root), "--catalog", "passives", "--yes", "--json")
    data = json.loads(r.stdout)
    assert data["written_files"] == 1 and data["failed_files"] == 0
    done = [f["path"].rsplit("/", 1)[1] for f in data["catalogs"][0]["files"] if f["done"]]
    assert done == ["resistors-dev.kicad_sch"]


# ---------------------------------------------------------------------------
# Symbols from the boards (1.6.0)
# ---------------------------------------------------------------------------


def stock_sheet(lib_id: str, mpn: str, footprint: str, count: int = 1, generator: str = "eeschema") -> str:
    """A board's sheet that draws ``mpn`` with a symbol of another library, as KiCad caches and places it."""
    nickname, _, name = lib_id.partition(":")
    cached = sc.PLACEHOLDER_SYMBOL.replace(f'(symbol "{sc.PLACEHOLDER}"', f'(symbol "{lib_id}"', 1)
    cached = cached.replace(sc.PLACEHOLDER, name).replace('(property "Reference" "X"', '(property "Reference" "U"')
    cached = cached.replace('(property "Value" "Catalog Placeholder"', f'(property "Value" "{name}"')
    start = cached.index('\t\t(property "Manufacturer PN"')
    cached = cached[:start] + cached[cached.index("\t\t(symbol ", start) :]  # a stock symbol has no such field
    cached = "\n".join("\t" + line if line else line for line in cached.split("\n"))
    placed = "".join(
        f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {20 * n} 50 0)\n\t\t(unit 1)\n'
        f'\t\t(property "Reference" "U{n}"\n\t\t\t(at 0 0 0)\n\t\t)\n'
        f'\t\t(property "Footprint" "{footprint}"\n\t\t\t(at 0 0 0)\n\t\t)\n'
        f'\t\t(property "Manufacturer PN" "{mpn}"\n\t\t\t(at 0 0 0)\n\t\t)\n\t)\n'
        for n in range(1, count + 1)
    )
    return (
        f'(kicad_sch\n\t(version 20260306)\n\t(generator "{generator}")\n\t(lib_symbols\n\t{cached}\n\t)\n{placed})\n'
    )


def test_a_part_without_a_library_symbol_takes_the_one_a_board_draws_it_with(tmp_path):
    root = make_root(tmp_path)
    write(
        stock_root := tmp_path / "stock", "Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod", footprint("SOT-23-5", None, 4)
    )
    assert stock_root.is_dir()
    ldo = "Regulator_Linear:TLV75533PDBV"
    write(root, "eps/kicad10/ldos.kicad_sch", stock_sheet(ldo, "tlv75533pdbvr", "Package_TO_SOT_SMD:SOT-23-5"))
    write(root, "mcu/kicad10/power.kicad_sch", stock_sheet("Other_Lib:LDO", "TLV75533PDBVR", "x:y", count=2))
    write(root, "mcu/kicad10/a.kicad_sch", stock_sheet(ldo, "TLV75533PDBVR", "Package_TO_SOT_SMD:SOT-23-5", count=2))
    # Not sources: a frozen copy, and anything this tool generated (the showcase would feed itself).
    write(root, "mcu/board-v1-frozen-dev/x.kicad_sch", stock_sheet("Frozen:STM", "STM32F405RGT7", ""))
    write(root, "mcu/kicad10/gen.kicad_sch", stock_sheet("Gen:STM", "STM32F405RGT7", "", generator=sc.GENERATOR))
    lib, shows = sc.build(root, settings(tmp_path), ["ics"])
    show = shows[0]
    how = {p.id: (p.how, sc._lib_id(lib, p.symbol)) for p in show.placements}
    assert how["ldo-500ma-sot23-5.tlv75533p"] == ("board", ldo)  # three placements against two, case aside
    assert lib.board["tlv75533pdbvr"].source == "eps/kicad10/ldos.kicad_sch"  # the first sheet by path
    assert how["ldo-500ma-sot23-5.tlv73333p-q1"] == ("slot", ldo)  # the drop-ins follow their reference
    assert how["mcu-lqfp64.stm32f405rgt7"][0] == "placeholder"
    assert how["can-xcvr-sot23-8.tcan334g"] == ("own", "bac Library Symbols v1:TI TCAN334")  # the library first
    found = kinds(show)
    assert found["board symbol"] == ["ldo-500ma-sot23-5.tlv75533p"]
    assert "ldo-500ma-sot23-5.tlv75533p" not in found.get("no symbol", []) + found.get("footprint missing", [])
    assert show.counts["With a symbol from a board"] == 1
    text = "".join(text_of(show, s.file) for s in show.sheets)
    sheet = parse(next(text_of(show, s.file) for s in show.sheets if f'(lib_id "{ldo}")' in text_of(show, s.file)))
    cache = [s.value(1) for s in sheet.child("lib_symbols").children("symbol")]
    assert ldo in cache and '(symbol "TLV75533PDBV_1_1"' in text
    instances = [s for s in sheet.children("symbol") if s.child("lib_id").value(1) == ldo]
    parts = sorted({p.value(1): p.value(2) for p in s.children("property")}["Manufacturer PN"] for s in instances)
    assert parts[0] == "TLV73333PQDBVRQ1" and "TLV75533PDBVR" in parts  # the field the stock symbol lacks
    assert all(len([p for p in s.children("property") if p.value(1) == "Manufacturer PN"]) == 1 for s in instances)
    board = parse(text_of(show, f"{show.project}.kicad_pcb"))
    assert any(fp.value(1) == "Package_TO_SOT_SMD:SOT-23-5" for fp in board.children("footprint"))
    write_all(shows)
    _, again = sc.build(root, settings(tmp_path), ["ics"])
    assert not again[0].pending  # the generated sheets are not read back as boards
    _, passives = sc.build(root, settings(tmp_path), ["passives"])
    assert passives[0].counts["With a symbol from a board"] == 0


def test_a_board_instance_of_a_library_symbol_uses_the_library_text(tmp_path):
    root = make_root(tmp_path)
    lib_id = "bac Library Symbols v1:bac R"  # a generic library symbol a board gives a part number
    write(root, "eps/kicad10/x.kicad_sch", stock_sheet(lib_id, "STM32F405RGT7", "Package_QFP:LQFP-64"))
    lib, shows = sc.build(root, settings(tmp_path), ["ics"])
    placed = next(p for p in shows[0].placements if p.id == "mcu-lqfp64.stm32f405rgt7")
    assert placed.how == "board" and placed.symbol.nickname == "" and placed.symbol.raw == lib.symbol("bac R").raw
    assert placed.footprint == "Package_QFP:LQFP-64"  # the row names none: the board's
    assert "mcu-lqfp64.stm32f405rgt7" in kinds(shows[0])["footprint from symbol"]


def cache_entry(text: str, lib_id: str) -> str:
    node = next(s for s in parse(text).child("lib_symbols").children("symbol") if s.value(1) == lib_id)
    return text[node.start : node.end]


def test_a_board_symbol_is_copied_as_cached_and_its_pins_are_flagged(tmp_path):
    root = make_root(tmp_path)
    mcu = "MCU_ST_STM32F4:STM32F405RGTx"
    source = stock_sheet(mcu, "STM32F405RGT7", "Package_QFP:LQFP-64").replace("(at -6.35 0 0)", "(at -8.89 0 0)")
    write(root, "mcu/kicad10/mcu.kicad_sch", source)
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    show = shows[0]
    text = next(text_of(show, s.file) for s in show.sheets if f'(lib_id "{mcu}")' in text_of(show, s.file))
    assert cache_entry(text, mcu) == cache_entry(source, mcu)  # byte for byte, indentation included
    sheet = parse(text)
    placed = next(s for s in sheet.children("symbol") if s.child("lib_id").value(1) == mcu)
    x, y = (float(v) for v in (placed.child("at").value(1), placed.child("at").value(2)))
    flags = {(float(f.child("at").value(1)), float(f.child("at").value(2))) for f in sheet.children("no_connect")}
    assert (round(x - 8.89, 4), y) in flags and (round(x + 6.35, 4), y) in flags


def test_a_showcase_sheet_kicad_saved_is_not_a_board(tmp_path):
    root = make_root(tmp_path)
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    write_all(shows)
    before = dict(shows[0].counts)
    for path in (root / "resources/catalog/ics/showcase").glob("*.kicad_sch"):
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(f'(generator "{sc.GENERATOR}")', '(generator "eeschema")'), encoding="utf-8")
    # The placeholder with a part number on a sheet elsewhere is no source either.
    write(root, "eps/kicad10/p.kicad_sch", stock_sheet(f"bac Library Symbols v1:{sc.PLACEHOLDER}", "STM32F405RGT7", ""))
    lib, again = sc.build(root, settings(tmp_path), ["ics"])
    assert not lib.board and dict(again[0].counts) == before


def test_board_symbols_that_are_parked_modified_or_further_units_do_not_count(tmp_path):
    root = make_root(tmp_path)
    nick = "bac Library Symbols v1"
    write(root, "a/kicad10/parked.kicad_sch", stock_sheet(f"{nick}:#unused ST STG3856QTR", "STG3856QTR", "x:y"))
    write(root, "a/kicad10/stale.kicad_sch", stock_sheet(f"{nick}:ST STG3856QTR", "STG3856QTR", "x:y"))
    modified = stock_sheet("Dev:MCU", "STM32F405RGT7", "x:y").replace("\t\t(unit 1)\n", '\t\t(lib_name "MCU_1")\n', 1)
    write(root, "a/kicad10/modified.kicad_sch", modified)
    units = stock_sheet("Dev:Quad", "TLV75533PDBVR", "x:y", count=3).replace("(unit 1)", "(unit 2)")
    write(root, "a/kicad10/units.kicad_sch", units)
    write(root, "b/kicad10/one.kicad_sch", stock_sheet("Dev:Single", "TLV75533PDBVR", "x:y"))
    lib, shows = sc.build(root, settings(tmp_path), ["ics"])
    assert sorted(lib.board) == ["tlv75533pdbvr"] and lib.board["tlv75533pdbvr"].name == "Single"
    found = kinds(shows[0])
    assert "mux-dual4-wqfn16.stg3856" in found["symbol #unused"] and "mcu-lqfp64.stm32f405rgt7" in found["no symbol"]


def test_board_symbol_ties_text_and_footprint(tmp_path):
    root = make_root(tmp_path)
    # Equal counts: the first by name. One text per symbol: the first sheet's, for every part number drawn with it.
    write(root, "a/kicad10/1.kicad_sch", stock_sheet("Dev:B", "STM32F405RGT7", "x:y"))
    write(root, "a/kicad10/2.kicad_sch", stock_sheet("Dev:A", "STM32F405RGT7", "x:y"))
    most = stock_sheet("Dev:A", "TLV75533PDBVR", "", count=3)
    write(root, "b/kicad10/3.kicad_sch", most.replace('(property "Footprint" ""', '(property "Footprint" "p:most"', 2))
    moved = stock_sheet("Dev:A", "TLV75533PDBVR", "p:aaa").replace("(at -6.35 0 0)", "(at -16.35 0 0)")
    write(root, "b/kicad10/4.kicad_sch", moved)
    lib, _ = sc.build(root, settings(tmp_path), ["ics"])
    mcu, ldo = lib.board["stm32f405rgt7"], lib.board["tlv75533pdbvr"]
    assert (mcu.nickname, mcu.name) == ("Dev", "A") and mcu.raw == ldo.raw and "-16.35" not in ldo.raw
    assert ldo.footprint == "p:most" and ldo.source == "b/kicad10/3.kicad_sch"  # two of four, an empty one aside


def test_board_symbol_fields_one_part_number_field_and_no_private_property(tmp_path):
    root = make_root(tmp_path)
    mcu = "Dev:MCU"
    source = stock_sheet(mcu, "STM32F405RGT7", "x:y")
    extra = '\t\t(property "manufacturer pn" "old"\n\t\t\t(at 0 0 0)\n\t\t)\n\t\t(property private "KLC_S3.3" "x"\n\t\t\t(at 0 0 0)\n\t\t)\n'
    at = source.index("\t\t\t(symbol ")
    write(root, "a/kicad10/m.kicad_sch", source[:at] + "\t" + extra.replace("\n\t", "\n\t\t")[:-1] + source[at:])
    _, shows = sc.build(root, settings(tmp_path), ["ics"])
    show = shows[0]
    text = next(text_of(show, s.file) for s in show.sheets if f'(lib_id "{mcu}")' in text_of(show, s.file))
    placed = next(s for s in parse(text).children("symbol") if s.child("lib_id").value(1) == mcu)
    fields = [(p.value(1), p.value(2)) for p in placed.children("property")]
    assert [f for f in fields if f[0].casefold() == "manufacturer pn"] == [("manufacturer pn", "STM32F405RGT7")]
    assert not any(name == "private" for name, _ in fields)
