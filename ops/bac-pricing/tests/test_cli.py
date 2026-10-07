# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from bac_pricing import NOTEBOOK, __version__
from bac_pricing import cli as cli_mod
from bac_pricing.cli import _main as main
from pricing_testkit import FIXTURES, write_db_config, write_files_config

from bac_common.testing import assert_standard_flags, invoke


def test_standard_flags():
    assert_standard_flags(main, "bac-pricing", __version__)


def test_missing_config_points_at_init(tmp_path):
    r = invoke(main, ["--config", str(tmp_path / "none.toml")])
    assert r.exit_code == 1 and "does not exist" in r.stderr


def test_dry_run_prints_the_marimo_command(tmp_path):
    cfg = write_files_config(tmp_path, FIXTURES)
    r = invoke(main, ["--config", str(cfg), "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "marimo edit" in r.stdout and str(NOTEBOOK) in r.stdout
    assert "files" in r.stdout and "dry run" in r.stdout
    r = invoke(main, ["--config", str(cfg), "--dry-run", "--app", "--port", "2719", "--headless"])
    assert "marimo run" in r.stdout and "--port 2719" in r.stdout and "--headless" in r.stdout


def test_db_mode_needs_a_dsn_and_shows_only_host_and_database(tmp_path, monkeypatch):
    cfg = write_db_config(tmp_path, FIXTURES)
    r = invoke(main, ["--config", str(cfg), "--dry-run"])
    assert r.exit_code == 1 and "BAC_DB_DSN" in r.stderr
    monkeypatch.setenv("BAC_DB_DSN", "postgresql://bac:pw@db.example:5432/bac")
    r = invoke(main, ["--config", str(cfg), "--dry-run"])
    assert r.exit_code == 0 and "db.example:5432/bac" in r.stdout and "pw" not in r.stdout


def test_public_bind_warns(tmp_path):
    cfg = write_files_config(tmp_path, FIXTURES)
    r = invoke(main, ["--config", str(cfg), "--dry-run", "--host", "0.0.0.0"])
    assert "no authentication" in r.stdout


def test_init_delegates_to_the_suite(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_mod, "run_init", lambda c, e: calls.append((c, e)))
    r = invoke(main, ["--init", "--config", "x.toml"])
    assert r.exit_code == 0 and calls == [("x.toml", None)]


def test_runs_marimo_with_the_settings_in_the_environment(tmp_path, monkeypatch):
    cfg = write_files_config(tmp_path, FIXTURES)
    seen = {}

    class Result:
        returncode = 0

    def fake_run(cmd, env, check):
        seen["cmd"], seen["env"] = cmd, env
        return Result()

    monkeypatch.setattr(cli_mod.subprocess, "run", fake_run)
    r = invoke(main, ["--config", str(cfg)])
    assert r.exit_code == 0, r.output
    assert seen["cmd"][1:4] == ["-m", "marimo", "edit"]
    assert seen["env"]["BAC_SUITE_CONFIG"] == str(cfg)


@pytest.mark.parametrize("code", [0, 3])
def test_exit_code_follows_marimo(tmp_path, monkeypatch, code):
    cfg = write_files_config(tmp_path, FIXTURES)

    class Result:
        returncode = code

    monkeypatch.setattr(cli_mod.subprocess, "run", lambda *a, **k: Result())
    assert invoke(main, ["--config", str(cfg)]).exit_code == (0 if code == 0 else 1)
