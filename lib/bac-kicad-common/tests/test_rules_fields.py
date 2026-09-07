# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from bac_common import sexp
from bac_common.errors import UsageError
from bac_kicad_common import fields, library, props, rules

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_rules_dir_orders_and_filters(rules_dir):
    sets = rules.load_rules_dir(rules_dir)
    assert [rs.path.name for rs in sets] == [
        "00-general.toml",
        "10-passives.toml",
        "30-footprints.toml",
        "60-project.toml",
    ]
    assert [rs.target for rs in rules.load_rules_dir(rules_dir, target="symbol")] == ["symbol", "symbol"]
    assert rules.load_rules_dir(rules_dir, target="schematic")[0].flags[0].name == "dnp"


def test_rules_for_precedence_and_when(rules_dir):
    sets = rules.load_rules_dir(rules_dir, target="symbol")
    ctx = rules.MatchContext("symbol", name="bac R", library="bac", prefix="R", properties={"Package": "0603"})
    chosen = rules.rules_for(sets, ctx)
    assert [r.name for r in chosen] == ["Manufacturer", "Datasheet URL", "Status", "Tolerance", "R Rated Power"]
    assert [r for r in chosen if r.name == "R Rated Power"][0].value == "0.2W"
    # A capacitor with no Package property never matches the `when` entries.
    ctx = rules.MatchContext("symbol", name="bac C", prefix="C", properties={})
    assert [r.name for r in rules.rules_for(sets, ctx)] == ["Manufacturer", "Datasheet URL", "Status", "Tolerance"]
    # An IC gets the general file only.
    ctx = rules.MatchContext("symbol", name="TI X", prefix="U")
    assert [r.name for r in rules.rules_for(sets, ctx)] == ["Manufacturer", "Datasheet URL", "Status"]


def test_schematic_matching_and_flags(rules_dir):
    sets = rules.load_rules_dir(rules_dir, target="schematic")
    r9 = rules.MatchContext("schematic", name="R", reference="R9", sheet="power.kicad_sch", lib_id="bac:R")
    assert [f.name for f in rules.flags_for(sets, r9)] == ["dnp"]
    r1 = rules.MatchContext("schematic", reference="R1", lib_id="bac:R")
    assert rules.flags_for(sets, r1) == [] and [f.name for f in rules.rules_for(sets, r1)] == ["Checked By"]
    assert rules.rules_for(sets, rules.MatchContext("schematic", reference="C1")) == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('target = "board"\n', "target must be one of"),
        ('target = "footprint"\n[match]\nreference_prefixes = ["R"]\n', "not valid for target 'footprint'"),
        ('[[field]]\nvalue = "x"\n', "missing 'name'"),
        ('target = "schematic"\n[[field]]\nname = "Reference"\n', "cannot be written on a schematic"),
        ('[[flag]]\nname = "dnp"\nvalue = true\n', "only supported for target 'schematic'"),
        ('target = "schematic"\n[[flag]]\nname = "hidden"\nvalue = true\n', "unknown flag"),
        ('target = "schematic"\n[[flag]]\nname = "dnp"\n', "missing 'value'"),
        ('[[field]]\nname = "X"\nwhen_name = "("\n', "bad regex"),
        ("title = [\n", "invalid TOML"),
        ('[[field]]\nname = "X"\nrequires = "Y"\n', "expected a list"),
        ('[[field]]\nname = "X"\nsize = "big"\n', "size must be a number"),
        ('[[field]]\nname = "X"\nwhen_reference = "^R"\n', "when_reference only applies to target 'schematic'"),
    ],
)
def test_rule_validation_errors(tmp_path, text, message):
    path = tmp_path / "bad.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(rules.RuleError, match=message):
        rules.load_ruleset(path)
    with pytest.raises(rules.RuleError, match="not found"):
        rules.load_rules_dir(tmp_path / "missing")
    (tmp_path / "empty").mkdir(exist_ok=True)
    with pytest.raises(rules.RuleError, match="No .toml"):
        rules.load_rules_dir(tmp_path / "empty")


def test_plan_fields_add_fill_set_and_skips(rules_dir):
    sets = rules.load_rules_dir(rules_dir, target="symbol")
    text, root = sexp.parse_file(FIXTURES / "bac-r.kicad_sym")
    target, items = library.containers(FIXTURES / "bac-r.kicad_sym", root)
    node, name = items[0]
    ps = props.properties(node)
    ctx = rules.MatchContext(
        "symbol",
        name=name,
        library=library.library_name(FIXTURES / "bac-r.kicad_sym"),
        prefix="R",
        properties={p.key: p.value for p in ps},
    )
    chosen = rules.rules_for(sets, ctx)

    plan = fields.plan_fields(chosen, ps)
    kinds = {(c.kind, c.key): c for c in plan.changes}
    assert ("add", "Status") in kinds and ("add", "Datasheet URL") not in kinds
    assert ("fill", "Manufacturer") not in kinds  # rule value is empty: nothing to fill
    assert ("Datasheet URL", "requires Manufacturer PN") in plan.skipped
    assert (
        "R Rated Power",
        "would overwrite '0.2W'; needs --allow-overwrite",
    ) not in plan.skipped  # 0603 → 0.2W already
    assert (
        plan.values["Tolerance"] == "1%"
        and ("Tolerance", "would overwrite '1%'; needs --allow-overwrite") not in plan.skipped
    )
    assert plan.touched and len(plan.adds) == 1 and plan.edits == []

    # Overwrite path: point the 0603 rule at another value.
    for rs in sets:
        for rule in rs.fields:
            if rule.name == "R Rated Power" and rule.value == "0.2W":
                rule.value = "0.25W"
    plan = fields.plan_fields(rules.rules_for(sets, ctx), ps)
    assert ("R Rated Power", "would overwrite '0.2W'; needs --allow-overwrite") in plan.skipped
    plan = fields.plan_fields(rules.rules_for(sets, ctx), ps, allow_overwrite=True)
    set_change = [c for c in plan.changes if c.kind == "set"][0]
    assert (set_change.key, set_change.previous, set_change.value) == ("R Rated Power", "0.2W", "0.25W")
    edited = sexp.apply_edits(text, plan.edits)
    assert '(property "R Rated Power" "0.25W"' in edited
    assert edited.replace('"0.25W"', '"0.2W"', 1) == text  # only that value changed

    # Fill path: an empty Manufacturer gets a value when a rule supplies one.
    manufacturer = [r for r in chosen if r.name == "Manufacturer"][0]
    manufacturer.value = "Yageo"
    plan = fields.plan_fields([manufacturer], ps)
    assert plan.changes[0].kind == "fill" and plan.edits[0][2] == '"Yageo"'
    plan = fields.plan_fields([manufacturer], ps, fill_empty=False)
    assert plan.changes == [] and not plan.touched


def test_substitute_and_requires_chain():
    values = {"Manufacturer PN": "RC0603", "Empty": ""}
    assert props.substitute("https://x/${Manufacturer PN}.pdf", values) == "https://x/RC0603.pdf"
    assert props.substitute("${Empty}", values) is None and props.substitute("${Nope}", values) is None
    rule_a = rules.FieldRule(name="A", value="a")
    rule_b = rules.FieldRule(name="B", value="${A}-b")
    plan = fields.plan_fields([rule_a, rule_b], [])
    assert [c.value for c in plan.changes] == ["a", "a-b"]


def test_render_property_shapes():
    rule = rules.FieldRule(name="MPN", value="", hide=True, size=0.762)
    sym10 = props.render_symbol_property(rule, "X", "\t\t", "\t", 20251024)
    assert sym10.split("\n") == [
        '\t\t(property "MPN" "X"',
        "\t\t\t(at 0 0 0)",
        "\t\t\t(show_name no)",
        "\t\t\t(do_not_autoplace no)",
        "\t\t\t(hide yes)",
        "\t\t\t(effects",
        "\t\t\t\t(font",
        "\t\t\t\t\t(size 0.762 0.762)",
        "\t\t\t\t)",
        "\t\t\t)",
        "\t\t)",
    ]
    sym9 = props.render_symbol_property(rules.FieldRule(name="MPN"), "X", "\t\t", "\t", 20241209)
    assert "(show_name" not in sym9 and sym9.index("(hide yes)") > sym9.index("(effects") and "(size 1.27 1.27)" in sym9
    fp = props.render_footprint_property(
        rules.FieldRule(name="Land Pattern", hide=False, layer="F.Fab"), "IPC", "\t", "\t", 0
    )
    assert (
        '(layer "F.Fab")' in fp
        and "(hide" not in fp
        and "(uuid " in fp
        and "(thickness 0.15)" in fp
        and "(size 1 1)" in fp
    )
    sch = props.render_schematic_property(rules.FieldRule(name="Checked By"), "MI", "\t\t", "\t", ("10.16", "20.32"))
    assert "(at 10.16 20.32 0)" in sch and sch.rstrip().endswith("\t\t)")
    # Values with quotes or newlines survive.
    assert (
        props.render_symbol_property(rule, 'a "b"\nc', "", "\t", 0).splitlines()[0] == '(property "MPN" "a \\"b\\"\\nc"'
    )


def test_properties_and_library_helpers(tmp_path):
    text, root = sexp.parse_file(FIXTURES / "bac-r.kicad_sym")
    target, items = library.containers(FIXTURES / "bac-r.kicad_sym", root)
    assert target == "symbol" and [name for _, name in items] == ["bac R"]
    ps = props.properties(items[0][0])
    assert len(ps) == 19 and ps[0].key == "Reference" and ps[0].value == "R"
    assert (
        text[ps[1].value_start : ps[1].value_end] == '"R"'
        and text[ps[1].node_start : ps[1].node_start + 17] == '(property "Value"'
    )
    assert props.property_value(items[0][0], "Footprint") == "bac KiCad Library Footprints v1:R-0603"
    assert props.property_value(items[0][0], "Nope") == ""

    text, root = sexp.parse_file(FIXTURES / "R-0603-100k.kicad_mod")
    target, items = library.containers(FIXTURES / "R-0603-100k.kicad_mod", root)
    assert target == "footprint" and items[0][1] == "R-0603-100k" and items[0][0] is root

    assert library.library_name(Path("/x/BAC_Passives.kicad_symdir/R.kicad_sym")) == "BAC_Passives"
    assert library.library_name(Path("/x/BAC_Passives.pretty/R.kicad_mod")) == "BAC_Passives"
    assert library.library_name(Path("/x/misc/R.kicad_mod")) == "misc"
    assert library.library_name(Path("/x/misc/bac-passives.kicad_sym")) == "bac-passives"
    assert rules.RuleError("x").exit_code == 2
    assert (
        library.reference_prefix("#PWR01") == "PWR"
        and library.reference_prefix("U") == "U"
        and library.reference_prefix("") == ""
    )

    found = library.find_files([FIXTURES, FIXTURES / "bac-r.kicad_sym"])
    assert [p.name for p in found] == [
        "R-0603-100k.kicad_mod",
        "TI-TPSM5D1806RDBR.kicad_mod",
        "bac-r.kicad_sym",
        "ti-tpsm5d1806rdbr.kicad_sym",
    ]
    with pytest.raises(UsageError, match="Not a KiCad library file"):
        library.find_files([FIXTURES / ".." / "conftest.py"])
    with pytest.raises(UsageError, match="No such file"):
        library.find_files([tmp_path / "nope"])
    with pytest.raises(sexp.SexpError, match="not a footprint file"):
        library.containers(Path("x.kicad_mod"), sexp.parse("(kicad_symbol_lib)"))
