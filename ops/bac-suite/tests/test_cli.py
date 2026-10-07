# SPDX-License-Identifier: MIT
from __future__ import annotations

from bac_suite import __version__
from bac_suite import cli as cli_mod
from bac_suite.cli import _main as main

from bac_common.testing import assert_standard_flags, invoke


def test_standard_flags():
    assert_standard_flags(main, "bac-suite", __version__)


def test_list_engines():
    r = invoke(main, ["-l"])
    assert r.exit_code == 0 and r.stdout.strip() == "Pricing\t/pricing"


def test_missing_config_points_at_init(tmp_path):
    r = invoke(main, ["--config", str(tmp_path / "none.toml")])
    assert r.exit_code == 1 and "does not exist" in r.stderr


def test_dry_run_lists_the_routes(files_config):
    r = invoke(main, ["--config", str(files_config), "--dry-run", "--port", "2720"])
    assert r.exit_code == 0, r.output
    assert "http://127.0.0.1:2720/pricing" in r.stdout and "dry run" in r.stdout
    assert "no authentication" not in r.stdout


def test_public_bind_warns(files_config):
    r = invoke(main, ["--config", str(files_config), "--dry-run", "--host", "0.0.0.0"])
    assert "no authentication" in r.stdout


def test_init_delegates_to_the_suite(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_mod, "run_init", lambda c, e: calls.append((c, e)))
    assert invoke(main, ["--init"]).exit_code == 0 and calls == [(None, None)]


def test_serves_with_uvicorn(files_config, monkeypatch):
    import uvicorn

    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    monkeypatch.setattr(cli_mod, "create_app", lambda tools: "app")
    r = invoke(main, ["--config", str(files_config), "--port", "2721"])
    assert r.exit_code == 0, r.output
    assert seen["host"] == "127.0.0.1" and seen["port"] == 2721
