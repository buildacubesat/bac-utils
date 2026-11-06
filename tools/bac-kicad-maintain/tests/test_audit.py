# SPDX-License-Identifier: MIT
"""The library audit on a small repository: usage, broken links, fields, the renames."""

from __future__ import annotations

from pathlib import Path

from bac_kicad_maintain import cli
from bac_kicad_maintain.audit import audit, load_repository, plan_renames

from bac_common.testing import invoke

PRETTY = "resources/kicad-libraries/footprints/lib.pretty"
SYMBOLS = "resources/kicad-libraries/symbols/lib.kicad_sym"
MODELS = "resources/kicad-libraries/3d"


def footprint(name: str, model: str | None = None, extra: str = "", datasheet: str = "", description: str = "") -> str:
    model_line = f'  (model "{model}" (offset (xyz 0 0 0)))\n' if model else ""
    return (
        f'(footprint "{name}" (version 20240108) (generator "pcbnew") (layer "F.Cu")\n'
        f'  (descr "{description}")\n'
        f'  (property "Reference" "REF**" (at 0 0 0) (layer "F.SilkS"))\n'
        f'  (property "Value" "{name}" (at 0 0 0) (layer "F.Fab"))\n'
        f'  (property "Datasheet" "{datasheet}" (at 0 0 0) (layer "F.Fab"))\n'
        f'  (property "Description" "{description}" (at 0 0 0) (layer "F.Fab"))\n'
        f"{extra}{model_line})\n"
    )


def symbol(name: str, fp: str, datasheet: str = "", description: str = "") -> str:
    return (
        f'  (symbol "{name}" (in_bom yes) (on_board yes)\n'
        f'    (property "Reference" "U" (at 0 0 0))\n'
        f'    (property "Value" "{name}" (at 0 0 0))\n'
        f'    (property "Footprint" "{fp}" (at 0 0 0))\n'
        f'    (property "Datasheet" "{datasheet}" (at 0 0 0))\n'
        f'    (property "Description" "{description}" (at 0 0 0))\n'
        f'    (symbol "{name}_0_1" (rectangle (start 0 0) (end 1 1))))\n'
    )


def placed(reference: str, lib_id: str, fp: str) -> str:
    return (
        f'  (symbol (lib_id "{lib_id}") (at 0 0 0) (uuid "{reference}")\n'
        f'    (property "Reference" "{reference}" (at 0 0 0))\n'
        f'    (property "Footprint" "{fp}" (at 0 0 0)))\n'
    )


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def make_repo(root: Path) -> Path:
    lib = "${BAC_LIB_DIR}"
    write(root, f"{PRETTY}/A.kicad_mod", footprint("A", f"{lib}/3d/A.step", datasheet="ds-a", description="A part"))
    write(root, f"{PRETTY}/B.kicad_mod", footprint("B", f"{lib}/3d/B.step"))
    write(root, f"{PRETTY}/R.kicad_mod", footprint("R", description="a package"))
    write(root, f"{PRETTY}/D.kicad_mod", footprint("D", f"{lib}/3d/D.step"))
    write(root, f"{PRETTY}/E.kicad_mod", footprint("E", extra='  (property "Heigh" "2 mm" (at 0 0 0))\n'))
    write(root, f"{PRETTY}/F.kicad_mod", footprint("F"))
    write(root, f"{PRETTY}/G.kicad_mod", footprint("G", "${KICAD9_3DMODEL_DIR}/x.step"))
    write(root, f"{PRETTY}/#unused-H.kicad_mod", footprint("#unused-H", f"{lib}/3d/H.step"))
    write(root, f"{PRETTY}/K.kicad_mod", footprint("K", f"{lib}/3d/gone.step"))
    for model in ("A.step", "B.step", "D.step", "H.step", "Orphan.step"):
        write(root, f"{MODELS}/{model}", "ISO-10303-21;\n")
    write(
        root,
        SYMBOLS,
        "(kicad_symbol_lib (version 20231120) (generator kicad_symbol_editor)\n"
        + symbol("Live A", "lib:A", datasheet="ds-a", description="A part")
        + symbol("#unused Dead B", "lib:B")
        + symbol("Live C", "lib:Missing")
        + symbol("Live Shared", "lib:R", description="a resistor")
        + symbol("Live Shared2", "lib:R", description="another resistor")
        + symbol("Orphan", "lib:K", datasheet="ds-k")
        + symbol("#unused Twin", "lib:H")
        + ")\n",
    )
    tables = (
        '(fp_lib_table (version 7)\n  (lib (name "lib") (type "KiCad") (uri "${BAC_LIB_DIR}/footprints/lib.pretty") (options "") (descr "")))\n',
        '(sym_lib_table (version 7)\n  (lib (name "lib") (type "KiCad") (uri "${BAC_LIB_DIR}/symbols/lib.kicad_sym") (options "") (descr ""))\n'
        '  (lib (name "gone") (type "KiCad") (uri "${BAC_LIB_DIR}/eps-v1/gone.kicad_sym") (options "") (descr ""))\n'
        '  (lib (name "std") (type "KiCad") (uri "${KICAD9_SYMBOL_DIR}/Device.kicad_sym") (options "") (descr "")))\n',
    )
    write(root, "boards/x/fp-lib-table", tables[0])
    write(root, "boards/x/sym-lib-table", tables[1])
    write(root, "boards/x/x.kicad_pro", "{}\n")
    write(
        root,
        "boards/x/x.kicad_sch",
        '(kicad_sch (version 20231120) (generator eeschema) (uuid "s") (paper "A4")\n'
        + placed("U1", "lib:Live A", "lib:A")
        + placed("R1", "lib:Live Shared", "lib:R")
        + placed("R2", "lib:Live Shared2", "lib:R")
        + placed("U2", "lib:Dead B", "")
        + placed("D1", "std:D", "Diode_SMD:D_0603")
        + ")\n",
    )
    write(
        root,
        "boards/x/x.kicad_pcb",
        '(kicad_pcb (version 20240108) (generator pcbnew) (paper "A4")\n'
        '  (footprint "lib:G" (layer "F.Cu") (uuid "g") (property "Reference" "J1" (at 0 0 0))\n'
        '    (model "${BAC_LIB_DIR}/3d/Orphan.step" (offset (xyz 0 0 0))))\n'
        '  (footprint "lib:Nope" (layer "F.Cu") (uuid "n") (property "Reference" "J2" (at 0 0 0)))\n'
        '  (footprint "Diode_SMD:D_0603" (layer "F.Cu") (uuid "d") (property "Reference" "D1" (at 0 0 0))))\n',
    )
    write(
        root,
        "resources/catalog/other/bac-other.csv",
        "id,mpn,footprint\np-1,X1,lib:F\np-2,X2,lib:Zed\np-3,X3,Package:SOT\n",
    )
    write(root, "resources/catalog/other/README.md", "# Other\n")
    return root


def load(root: Path):
    return load_repository(root, Path("resources/kicad-libraries"), [Path("resources/catalog/other")])


def kinds(items) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in items:
        out.setdefault(f.kind, []).append(f.subject)
    return out


def test_usage_rule_and_findings(tmp_path):
    repo = make_repo(tmp_path)
    report = audit(load(repo))
    assert [f.subject for f in report.unused_footprints] == ["B", "D", "E"]
    assert "referenced by symbol #unused Dead B only" in report.unused_footprints[0].detail
    assert "nothing references it" in report.unused_footprints[1].detail
    # A: live symbol; F: catalog row; G: board; K: symbol Orphan (live, even if unplaced); R: live symbols.
    # Orphan.step: the board uses it; H.step: only the prefixed footprint points at it.
    assert [f.subject for f in report.unused_models] == ["3d/B.step", "3d/D.step", "3d/H.step"]
    broken = kinds(report.broken_links)
    assert broken["symbol footprint"] == ["#unused Twin", "Live C"]
    assert "the library has it as '#unused-H'" in report.broken_links[0].detail
    assert broken["placed symbol"] == ["U2 lib:Dead B"]
    assert "the library has it as '#unused Dead B'" in next(
        f.detail for f in report.broken_links if f.kind == "placed symbol"
    )
    assert broken["board footprint"] == ["J2 lib:Nope"]
    assert broken["catalog footprint"] == ["lib:Zed"]
    assert broken["footprint model"] == ["K"]
    fields = kinds(report.field_mismatches)
    assert fields["nonstandard field"] == ["E"]
    assert fields["Datasheet"] == ["K"]  # Orphan says ds-k, the footprint says nothing
    assert "Description" not in fields  # R is shared by two live symbols: the package description is its own
    assert kinds(report.symbols)["symbol not placed"] == ["Live C", "Orphan"]
    assert kinds(report.libraries)["library missing"] == ["gone"]
    assert report.libraries[0].where == "boards/x" and "sym-lib-table points at" in report.libraries[0].detail
    assert report.counts["boards"] == 1 and report.counts["sheets"] == 1 and report.counts["catalog files"] == 1


def test_descr_mismatch_and_twin_hint(tmp_path):
    repo = make_repo(tmp_path)
    path = repo / PRETTY / "A.kicad_mod"
    path.write_text(path.read_text().replace('(descr "A part")', '(descr "old text")'), newline="")
    sym = repo / SYMBOLS
    sym.write_text(sym.read_text().replace('"lib:B"', '"lib:#unused-H"'), newline="")
    report = audit(load(repo))
    assert kinds(report.field_mismatches)["descr"] == ["A"]
    assert "B" in [f.subject for f in report.unused_footprints]
    assert "nothing references it" in next(f.detail for f in report.unused_footprints if f.subject == "B")


def test_plan_renames_follow_references(tmp_path):
    repo = make_repo(tmp_path)
    loaded = load(repo)
    renames, symbol_text = plan_renames(loaded, audit(loaded))
    moves = {r.path.name: (r.new_path.name, r.reason) for r in renames}
    assert moves["B.kicad_mod"] == ("#unused-B.kicad_mod", "unused footprint")
    assert moves["D.kicad_mod"] == ("#unused-D.kicad_mod", "unused footprint")
    assert moves["E.kicad_mod"] == ("#unused-E.kicad_mod", "unused footprint")
    assert moves["#unused-H.kicad_mod"] == ("#unused-H.kicad_mod", "its model was renamed")
    assert moves["B.step"] == ("#unused-B.step", "unused model")
    assert moves["D.step"] == ("#unused-D.step", "unused model")
    assert moves["H.step"] == ("#unused-H.step", "unused model")
    assert len(moves) == 7
    b = next(r for r in renames if r.path.name == "B.kicad_mod")
    assert '(footprint "#unused-B"' in b.text and "${BAC_LIB_DIR}/3d/#unused-B.step" in b.text
    assert symbol_text is not None
    assert '(property "Footprint" "lib:#unused-B"' in symbol_text
    assert '(property "Footprint" "lib:#unused-H"' in symbol_text  # the twin that was prefixed earlier
    assert symbol_text.count("#unused-") == 2


def test_check_and_apply_on_the_command_line(tmp_path):
    repo = make_repo(tmp_path)
    r = invoke(cli._main, ["check", str(repo), "--audit"])
    assert r.exit_code == 1 and "unused footprints (3)" in r.stdout and "library missing" in r.stdout
    r = invoke(cli._main, ["check", str(repo), "--audit", "--json"])
    assert r.exit_code == 1 and '"unused_footprints"' in r.stdout
    r = invoke(cli._main, ["apply", str(repo), "--audit", "--dry-run"])
    assert r.exit_code == 0 and "B.kicad_mod → #unused-B.kicad_mod" in r.stdout and "dry run" in r.stdout
    assert (repo / PRETTY / "B.kicad_mod").exists()
    r = invoke(cli._main, ["apply", str(repo), "--audit", "--yes"])
    assert r.exit_code == 0, r.stdout + r.stderr
    pretty = repo / PRETTY
    assert not (pretty / "B.kicad_mod").exists() and (pretty / "B.kicad_mod.bak").exists()
    assert (pretty / "#unused-B.kicad_mod").read_text().startswith('(footprint "#unused-B"')
    assert (repo / MODELS / "#unused-D.step").exists() and not (repo / MODELS / "D.step").exists()
    assert not (repo / MODELS / "D.step.bak").exists()  # a model is moved, not copied
    assert (repo / SYMBOLS).with_name("lib.kicad_sym.bak").exists()
    r = invoke(cli._main, ["check", str(repo), "--audit"])
    assert "unused footprints" not in r.stdout and "unused models" not in r.stdout
    assert r.exit_code == 1  # the broken links and field mismatches remain for a person


def test_apply_refuses_the_whole_batch_on_a_lock_or_a_changed_file(tmp_path):
    repo = make_repo(tmp_path)
    lock = (repo / SYMBOLS).with_name("~lib.kicad_sym.lck")
    lock.write_text("")
    r = invoke(cli._main, ["apply", str(repo), "--audit", "--yes", "--no-backup"])
    assert r.exit_code == 1 and "close it first" in r.stderr
    assert (repo / PRETTY / "B.kicad_mod").exists() and not (repo / PRETTY / "#unused-B.kicad_mod").exists()
    assert "#unused-B" not in (repo / SYMBOLS).read_text()
    lock.unlink()
    # A footprint edited between planning and writing stops the batch too; the plan is made before the prompt.
    b = repo / PRETTY / "B.kicad_mod"
    original = b.read_text()

    def tamper(*args, **kwargs):
        b.write_text(original + "\n", newline="")

    import bac_kicad_maintain.cli as cli_module

    cli_module.confirm = lambda question, *, yes=False: tamper()
    try:
        r = invoke(cli._main, ["apply", str(repo), "--audit"])
    finally:
        from bac_kicad_common.files import confirm

        cli_module.confirm = confirm
    assert r.exit_code == 1 and "changed after it was planned" in r.stdout
    assert b.exists() and not (repo / PRETTY / "#unused-B.kicad_mod").exists()  # B is left alone and reported
    assert (repo / MODELS / "#unused-D.step").exists()  # the rest of the batch goes through


def test_a_nickname_the_project_table_lacks_still_counts(tmp_path):
    """The breadboard case: the board says 'bac KiCad …', its own table says 'bac …' – the placements count."""
    repo = make_repo(tmp_path)
    board = repo / "boards/x/x.kicad_pcb"
    board.write_text(board.read_text().replace('(footprint "lib:G"', '(footprint "other:G"'), newline="")
    other = repo / "boards/y"
    other.mkdir()
    (other / "y.kicad_pro").write_text("{}\n")
    (other / "fp-lib-table").write_text(
        '(fp_lib_table (version 7)\n  (lib (name "other") (type "KiCad") (uri "${BAC_LIB_DIR}/footprints/lib.pretty") (options "") (descr "")))\n'
    )
    (other / "y.kicad_sch").write_text('(kicad_sch (version 1) (generator eeschema) (paper "A4"))\n')
    report = audit(load(repo))
    assert "G" not in [f.subject for f in report.unused_footprints]
    foreign = [f for f in report.libraries if f.kind == "nickname not in table"]
    assert [(f.subject, f.where) for f in foreign] == [("other", "boards/x")]
    assert "x.kicad_pcb; fp-lib-table does not define it" in foreign[0].detail


def test_a_live_symbol_on_a_missing_footprint_is_not_rewritten(tmp_path):
    repo = make_repo(tmp_path)
    sym = repo / SYMBOLS
    head, sep, _ = sym.read_text().rpartition(")\n")
    sym.write_text(head + symbol("Live Needs H", "lib:H") + sep, newline="")
    loaded = load(repo)
    report = audit(loaded)
    _, symbol_text = plan_renames(loaded, report)
    assert symbol_text is not None
    assert symbol_text.count('"lib:#unused-H"') == 1  # the #unused Twin follows, Live Needs H stays broken
    assert '(property "Footprint" "lib:H"' in symbol_text
    assert any(f.subject == "Live Needs H" for f in report.broken_links)


def test_a_model_path_is_renamed_on_its_last_component_only(tmp_path):
    repo = make_repo(tmp_path)
    d = repo / PRETTY / "D.kicad_mod"
    d.write_text(d.read_text().replace("${BAC_LIB_DIR}/3d/D.step", "${BAC_LIB_DIR}/3d/./D.step"), newline="")
    b = repo / PRETTY / "B.kicad_mod"
    b.write_text(b.read_text().replace("${BAC_LIB_DIR}/3d/B.step", "${BAC_LIB_DIR}/3d/B.step/."), newline="")
    loaded = load(repo)
    report = audit(loaded)
    renames, _ = plan_renames(loaded, report)
    assert [f.subject for f in report.unused_models] == ["3d/B.step", "3d/D.step", "3d/H.step"]
    d_rename = next(r for r in renames if r.path.name == "D.kicad_mod")
    assert "${BAC_LIB_DIR}/3d/./#unused-D.step" in d_rename.text and "3d3d" not in d_rename.text
    b_rename = next(r for r in renames if r.path.name == "B.kicad_mod")
    assert "${BAC_LIB_DIR}/3d/B.step/." in b_rename.text  # not spelled by its name: left alone
    assert [f.subject for f in report.libraries if f.kind == "model path"] == ["B"]


def test_a_twin_that_exists_already_is_skipped_and_reported(tmp_path):
    repo = make_repo(tmp_path)
    (repo / PRETTY / "#unused-D.kicad_mod").write_text(footprint("#unused-D"), newline="")
    (repo / MODELS / "#unused-B.step").write_text("ISO-10303-21;\n")
    loaded = load(repo)
    report = audit(loaded)
    renames, symbol_text = plan_renames(loaded, report)
    moves = {r.path.name: r.new_path.name for r in renames}
    assert moves["D.kicad_mod"] == "D.kicad_mod"  # edited in place for its model, not prefixed
    assert "B.step" not in moves and moves["B.kicad_mod"] == "#unused-B.kicad_mod"
    twins = [f for f in report.libraries if f.kind == "twin"]
    assert [f.subject for f in twins] == ["D", "3d/B.step"]
    assert '"lib:#unused-B"' in (symbol_text or "")
    r = invoke(cli._main, ["apply", str(repo), "--audit", "--yes", "--no-backup"])
    assert r.exit_code == 0, r.stdout + r.stderr
    r = invoke(cli._main, ["apply", str(repo), "--audit", "--dry-run"])
    assert "D.kicad_mod →" not in r.stdout and "Files to rename or edit  :  0" in r.stdout


def test_missing_libraries_are_reported_per_table(tmp_path):
    repo = make_repo(tmp_path)
    table = repo / "boards/x/fp-lib-table"
    table.write_text(
        table.read_text().replace(
            ")))\n",
            '))\n  (lib (name "gone") (type "KiCad") (uri "${BAC_LIB_DIR}/eps-v1/gone.pretty") (options "") (descr "")))\n',
        ),
        newline="",
    )
    report = audit(load(repo))
    missing = [(f.subject, f.detail.split(" points")[0]) for f in report.libraries if f.kind == "library missing"]
    assert missing == [("gone", "fp-lib-table"), ("gone", "sym-lib-table")]


def test_audit_usage_errors(tmp_path):
    repo = make_repo(tmp_path)
    r = invoke(cli._main, ["check", str(repo), "--audit", "--text"])
    assert r.exit_code == 2 and "runs on its own" in r.stderr
    r = invoke(cli._main, ["check", str(repo / "boards"), str(repo), "--audit"])
    assert r.exit_code == 2 and "one directory" in r.stderr
    r = invoke(cli._main, ["check", str(repo), "--audit", "--diff"])
    assert r.exit_code == 2 and "no diff" in r.stderr
    r = invoke(cli._main, ["check", str(repo), "--audit", "--exclude", "boards/*"])
    assert r.exit_code == 2 and "--exclude does not apply" in r.stderr
    r = invoke(cli._main, ["check", str(repo / "boards"), "--audit"])
    assert r.exit_code == 2 and "No library folder" in r.stderr
    r = invoke(cli._main, ["apply", str(repo), "--audit", "--json"])
    assert r.exit_code == 2 and "--yes" in r.stderr


def test_library_and_catalogs_from_the_config(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "resources/catalog/other").rename(repo / "resources/other")
    config = tmp_path / "maintain.toml"
    config.write_text('[audit]\nlibrary = "resources/kicad-libraries"\ncatalogs = ["resources/other"]\n')
    r = invoke(cli._main, ["--config", str(config), "check", str(repo), "--audit", "--json"])
    assert r.exit_code == 1 and '"catalog files": 1' in r.stdout
    config.write_text('[audit]\ncatalogs = ["nowhere"]\n')
    r = invoke(cli._main, ["--config", str(config), "check", str(repo), "--audit", "--json"])
    assert '"catalog files": 0' in r.stdout and "lib:F" not in r.stdout
    assert '"subject": "F"' in r.stdout  # without the catalog, F is unused
