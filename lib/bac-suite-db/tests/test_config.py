# SPDX-License-Identifier: MIT
from __future__ import annotations

import tomllib

import pytest

from bac_common.errors import ConfigError
from bac_suite_db import config


def test_settings_from_explicit_config(suite_config, tmp_path):
    s = config.load_settings(suite_config)
    assert s.backend == "postgres"
    assert s.uses_db
    assert s.data_dir == tmp_path / "data"
    assert s.config_path == suite_config
    assert s.dsn is None


def test_env_var_names_the_config(suite_config, monkeypatch):
    monkeypatch.setenv(config.CONFIG_ENV, str(suite_config))
    assert config.load_settings().config_path == suite_config


def test_relative_data_dir_resolves_against_the_config_file(tmp_path):
    path = tmp_path / "bac-suite.toml"
    path.write_text('[storage]\nbackend = "files"\ndata_dir = "ops-data"\n')
    s = config.load_settings(path)
    assert s.data_dir == (tmp_path / "ops-data").resolve()
    assert not s.uses_db


def test_data_dir_env_wins(suite_config, monkeypatch, tmp_path):
    monkeypatch.setenv(config.DATA_DIR_ENV, str(tmp_path / "elsewhere"))
    assert config.load_settings(suite_config).data_dir == tmp_path / "elsewhere"


def test_bad_backend_is_a_config_error(tmp_path):
    path = tmp_path / "bac-suite.toml"
    path.write_text('[storage]\nbackend = "sqlite"\n')
    with pytest.raises(ConfigError, match="sqlite"):
        config.load_settings(path)


def test_explicit_missing_config_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="does not exist"):
        config.load_settings(tmp_path / "none.toml")


def test_require_setup_points_at_init(tmp_path):
    with pytest.raises(ConfigError, match="not set up") as info:
        config.require_setup(config.Settings("postgres", tmp_path, None, tmp_path / "missing.toml", None))
    assert "--init" in info.value.detail


def test_dsn_from_env_and_from_the_data_dir_env_file(suite_config, tmp_path, monkeypatch):
    assert config.load_settings(suite_config).dsn is None
    (tmp_path / "data" / ".env").write_text("BAC_DB_DSN=postgresql://u:p@h/d\n")
    s = config.load_settings(suite_config)
    assert s.dsn == "postgresql://u:p@h/d"
    assert s.env_path == tmp_path / "data" / ".env"
    monkeypatch.setenv(config.DSN_ENV, "postgresql://other/d")
    assert config.load_settings(suite_config).dsn == "postgresql://other/d"


def test_explicit_env_file(suite_config, tmp_path):
    env = tmp_path / "custom.env"
    env.write_text("BAC_DB_DSN=postgresql://x/y\n")
    s = config.load_settings(suite_config, env)
    assert s.dsn == "postgresql://x/y" and s.env_path == env


def test_require_dsn_errors_name_the_fix(suite_config, files_config, tmp_path):
    with pytest.raises(ConfigError, match="BAC_DB_DSN"):
        config.require_dsn(config.load_settings(suite_config))
    with pytest.raises(ConfigError, match="files") as info:
        config.require_dsn(config.load_settings(files_config))
    assert "BAC_DB_DSN" in info.value.detail


def test_templates_are_valid_toml_and_dotenv():
    toml = config.config_template("~/bac/ops-data", "files")
    parsed = tomllib.loads(toml)
    assert parsed["storage"] == {"backend": "files", "data_dir": "~/bac/ops-data"}
    assert "–" in toml and "\u2014" not in toml
    env = config.env_template("postgresql://bac@localhost/bac")
    assert env.rstrip().splitlines()[-1] == "BAC_DB_DSN=postgresql://bac@localhost/bac"


def test_data_dir_env_is_found_behind_a_nearer_env_of_another_tool(suite_config, tmp_path, monkeypatch):
    """A .env above the working directory that belongs to another tool must not hide the one --init wrote."""
    (tmp_path / ".env").write_text("OTHER_TOOL_TOKEN=abc\n")
    (tmp_path / "data" / ".env").write_text("BAC_DB_DSN=postgresql://u:p@h/d\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    s = config.load_settings(suite_config)
    assert s.dsn == "postgresql://u:p@h/d"
    assert s.env_path == tmp_path / "data" / ".env"


def test_init_template_escapes_backslashes():
    toml = config.config_template("C:\\Users\\m\\bac\\ops-data")
    assert tomllib.loads(toml)["storage"]["data_dir"] == "C:\\Users\\m\\bac\\ops-data"
