# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest
from bac_convention_check.builtins import BUILTINS
from bac_convention_check.engine import FileIndex, enumerate_files, path_matches, run_rules
from bac_convention_check.rules import Rule, load_rule_set, load_rules

from bac_common.errors import ConfigError


def scan(root: Path, sets=("guide",), **kwargs):
    files, _ = enumerate_files(root)
    index = FileIndex(root, files)
    results = run_rules(load_rules(list(sets)), index, builtins=BUILTINS, **kwargs)
    return {r.rule.id: r for r in results}


# Rule id → (expected hit count, substring expected in one hit) for the dirty tree.
EXPECTED = {
    "A1": (1, "em dash"),
    "A2": (1, "100x100"),
    "A3": (1, "🚀"),
    "A4": (1, "curly"),
    "A5": (1, "quoted"),
    "A6": (1, "Straße"),
    "A7": (1, "12,059 CHF"),
    "B1": (1, "Bac project"),
    "B2": (1, "buildacubesat says"),
    "B3": (1, "Bac-notes.txt"),
    "F1": (1, "Internal Tools Design Language"),
    "H1": (1, "API_KEY"),
    "H2": (1, "config-v1.2.yml"),
    "L1": (1, "src/demo/cli.py"),
    "L2": (1, "no-license/pyproject.toml"),
    "L3": (1, "table form"),
    "P1": (1, ">=3.10"),
    "P2": (1, "setuptools"),
    "P3": (2, "rich<14"),
    "P4": (1, "demo-tool"),
    "P5": (2, "demo.main:run"),
    "V1": (1, "src/demo/cli.py"),
    "V2": (1, "config-v1.2.yml"),
    "R1": (1, "README.md"),
    "R2": (1, "README.md"),
    "U1": (1, "bac-hardware"),
    "S1": (1, "SPI master"),
}


def test_every_guide_rule_fires_once_on_the_dirty_tree(dirty):
    results = scan(dirty)
    assert set(results) == set(EXPECTED), "rule set changed; update EXPECTED"
    for rule_id, (count, needle) in EXPECTED.items():
        r = results[rule_id]
        assert r.error is None, (rule_id, r.error)
        assert r.count == count, (rule_id, [f"{h.path}:{h.line}:{h.text}" for h in r.hits])
        assert any(needle in f"{h.path}:{h.text}" for h in r.hits), (rule_id, needle, r.hits)


def test_clean_tree_is_clean(clean):
    results = scan(clean)
    noisy = {k: [f"{h.path}:{h.line}:{h.text}" for h in v.hits] for k, v in results.items() if v.count or v.error}
    assert noisy == {}


def test_binary_files_are_skipped(clean):
    results = scan(clean)
    assert results["A1"].count == 0  # image.bin contains an em dash after a NUL byte


def test_config_excludes_per_rule_and_global(dirty):
    results = scan(dirty, excludes={"A1": ["README.md"]})
    assert results["A1"].count == 0 and results["A4"].count == 1
    results = scan(dirty, excludes={"*": ["README.md", "**/pyproject.toml", "src/**"]})
    assert results["A1"].count == 0 and results["L2"].count == 0 and results["H1"].count == 0


def test_inline_allow_marker(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.md").write_text(
        "one — em dash\ntwo — em dash  <!-- convention-check: allow A1 -->\n"
        "three — ‘x’ <!-- convention-check: allow all -->\nfour — <!-- convention-check: allow B1, A1 -->\n"
    )
    results = scan(root)
    assert results["A1"].count == 1
    assert results["A4"].count == 0


def test_counts_are_full_even_when_output_is_truncated(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.md").write_text("\n".join(f"line {i} — dash" for i in range(50)) + "\n")
    results = scan(root)
    assert results["A1"].count == 50


def test_git_enumeration_honours_gitignore_and_includes_untracked(git_repo):
    files, source = enumerate_files(git_repo)
    assert source == "git ls-files"
    assert "untracked.md" in files and "ignored/x.md" not in files
    files, source = enumerate_files(git_repo, use_git=False)
    assert source == "directory walk"
    assert "ignored/x.md" in files


def test_path_matching():
    assert path_matches("a/b/c.py", "*.py")
    assert path_matches("a/b/cli.py", "**/cli.py")
    assert path_matches("cli.py", "**/cli.py")
    assert path_matches(".github/workflows/ci.yml", ".github/**")
    assert path_matches("x/zephyr/y.yml", "**/zephyr/**")
    assert not path_matches("a/b/c.py", "*.md")
    assert not path_matches("src/README.md", "README.md") or path_matches("src/README.md", "**/README.md")
    assert path_matches("Kconfig.board", "Kconfig*")


def test_rule_set_validation(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('[[rules]]\nid = "X1"\ntitle = "t"\nseverity = "blocking"\nkind = "regex"\npattern = "(unclosed"\n')
    with pytest.raises(ConfigError, match="invalid pattern regex"):
        load_rule_set(bad)
    bad.write_text('[[rules]]\nid = "X1"\ntitle = "t"\nseverity = "maybe"\nkind = "regex"\npattern = "x"\n')
    with pytest.raises(ConfigError, match="severity"):
        load_rule_set(bad)
    bad.write_text('[[rules]]\nid = "A1"\ntitle = "t"\nseverity = "blocking"\nkind = "regex"\npattern = "x"\n')
    with pytest.raises(ConfigError, match="defined in both"):
        load_rules(["guide", str(bad)])
    with pytest.raises(ConfigError, match="Rule set not found"):
        load_rules(["nope"])


def test_unknown_builtin_is_a_rule_error_not_a_crash(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.md").write_text("x\n")
    rule = Rule(id="Z1", title="t", severity="blocking", kind="builtin", builtin="does_not_exist")
    results = run_rules([rule], FileIndex(root, ["a.md"]))
    assert results[0].error and "unknown builtin" in results[0].error


def test_firmware_rules_load_and_analyse(tmp_path):
    root = tmp_path / "fw"
    (root / "docs").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "docs" / "tn.md").write_text("Uses the ADS1113 and the TCAN1042 plus TJA1051 and BNO086.\n")
    (root / "src" / "main.c").write_text(
        "#define BAC_NODE 1\n#define ROCI_ADDR 31\nstatic char buf[64];\nU8 aliveNodes;\n"
        "gpio_pin_set(dev, 1, 1);\ncsp_send(conn, p);\nti,ads1113@48\n"
    )
    (root / "app.overlay").write_text("ti,ads1113@48 { };\n")
    results = scan(root, sets=("firmware",))
    assert results["E1"].count == 1 and results["E2"].count == 2
    assert results["E8"].count == 1 and "more than one family" in " ".join(results["E8"].notes)
    assert results["D2"].count == 1 and results["G1"].count == 1 and results["G2"].count == 1
    assert results["G3"].count == 1
    assert results["C1"].count == 1 and "both prefixes" in " ".join(results["C1"].notes)
    orphan_parts = [h.text.split(":")[0] for h in results["E9"].hits]
    assert orphan_parts == ["BNO086", "TCAN1042"]  # ADS1113 is in the overlay; TJA1051 is not a tracked family
