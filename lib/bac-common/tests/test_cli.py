# SPDX-License-Identifier: MIT
from __future__ import annotations

from demo_tool import TOOL, VERSION, main

from bac_common import cli
from bac_common.testing import assert_standard_flags, invoke


def _configured(tmp_path):
    cfg = tmp_path / "demo.toml"
    cfg.write_text('[paths]\ntarget = "/tmp/demo"\n', encoding="utf-8")
    return cfg


def test_standard_flag_contract():
    assert_standard_flags(main, TOOL, VERSION)


def test_version_output_has_v_prefix():
    assert invoke(main, ["--version"]).stdout.strip() == "bac-demo v0.2.0"


def test_help_lists_standard_flags_and_examples():
    text = invoke(main, ["--help"]).stdout
    for flag in ("-v, --version", "-l, --list", "--env-file PATH", "--config PATH", "--dry-run", "--init"):
        assert flag in text, flag
    assert "Examples:" in text
    assert "bac-demo ./docs --dry-run" in text
    assert "--debug" not in text


def test_help_text_helper_counts_lines():
    parser = cli.make_parser("bac-x", "1.0.0", "One sentence.", examples=["bac-x a", "bac-x b"])
    lines = cli.help_text(parser).rstrip("\n").splitlines()
    assert len(lines) <= 24


def test_list_flag_prints_plain_items():
    result = invoke(main, ["-l"])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == ["alpha", "beta", "gamma"]


def test_missing_setup_points_to_init():
    result = invoke(main, ["some-dir"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "ERROR bac-demo is not set up" in result.stderr
    assert "bac-demo --init" in result.stderr


def test_init_writes_config_then_tool_runs(tmp_path):
    cfg = tmp_path / "demo.toml"
    init = invoke(main, ["--init", "--config", str(cfg)])
    assert init.exit_code == 0, init.output
    assert cfg.read_text(encoding="utf-8").startswith("[paths]")

    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.txt").write_text("x")
    result = invoke(main, [str(tmp_path / "in"), "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "bac-demo" in result.stdout and "v0.2.0" in result.stdout
    assert "✓ Counted 1 file(s)" in result.stdout
    assert "Files   :  1" in result.stdout


def test_dry_run_label_in_summary(tmp_path):
    cfg = _configured(tmp_path)
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.txt").write_text("x")
    result = invoke(main, [str(tmp_path / "in"), "--config", str(cfg), "--dry-run"])
    assert "(dry run – no changes made)" in result.stdout


def test_return_code_is_exit_code(tmp_path):
    cfg = _configured(tmp_path)
    (tmp_path / "empty").mkdir()
    assert invoke(main, [str(tmp_path / "empty"), "--config", str(cfg)]).exit_code == 3


def test_bac_error_renders_on_stderr_with_detail(tmp_path):
    cfg = _configured(tmp_path)
    result = invoke(main, ["--boom", "config", "--config", str(cfg)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.splitlines()[0] == "ERROR Something is not configured."
    assert result.stderr.splitlines()[1].strip() == "Set it and retry."
    assert "Traceback" not in result.stderr


def test_debug_shows_traceback_and_is_accepted_anywhere(tmp_path):
    cfg = _configured(tmp_path)
    result = invoke(main, ["--boom", "config", "--config", str(cfg), "--debug"])
    assert result.exit_code == 1
    assert "Traceback" in result.stderr
    result = invoke(main, ["--debug", "--boom", "config", "--config", str(cfg)])
    assert "Traceback" in result.stderr


def test_user_abort_exits_zero_quietly(tmp_path):
    cfg = _configured(tmp_path)
    result = invoke(main, ["--boom", "abort", "--config", str(cfg)])
    assert result.exit_code == 0
    assert result.stdout.strip() == "Aborted."
    assert result.stderr == ""


def test_unexpected_exception_is_one_line_and_escaped(tmp_path):
    cfg = _configured(tmp_path)
    result = invoke(main, ["--boom", "crash", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "ERROR Unexpected error: unexpected [red]markup[/] in message" in result.stderr
    assert "Re-run with --debug" in result.stderr
    assert "Traceback" not in result.stderr


def test_unexpected_exception_raises_under_debug(tmp_path):
    import pytest

    cfg = _configured(tmp_path)
    with pytest.raises(ValueError):
        invoke(main, ["--boom", "crash", "--config", str(cfg), "--debug"])


def test_keyboard_interrupt_exits_one(tmp_path):
    cfg = _configured(tmp_path)
    result = invoke(main, ["--boom", "interrupt", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "Interrupted." in result.stdout


def test_bad_arguments_exit_two():
    result = invoke(main, ["--no-such-flag"])
    assert result.exit_code == 2
    assert "usage:" in result.stderr


def test_strip_debug():
    assert cli.strip_debug(["a", "--debug", "b"]) == (["a", "b"], True)
    assert cli.strip_debug(["a", "b"]) == (["a", "b"], False)


def test_version_string():
    assert cli.version_string("bac-x", "1.2.3") == "bac-x v1.2.3"
    assert cli.version_string("bac-x", "v1.2.3") == "bac-x v1.2.3"


def test_parser_without_optional_flags():
    parser = cli.make_parser("bac-x", "1.0.0", "Simple.", init=False, dry_run=False, env_file=False, config=False)
    text = cli.help_text(parser)
    assert "-v, --version" in text
    for absent in ("--init", "--dry-run", "--env-file", "--config", "--list"):
        assert absent not in text, absent
