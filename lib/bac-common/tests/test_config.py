# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import stat

import pytest

from bac_common import config
from bac_common.errors import ConfigError


def test_default_config_path_uses_bac_dir(isolated_config_dir):
    assert config.default_config_path("bac-x") == isolated_config_dir / "bac-x.toml"


def test_load_toml_missing_default_is_empty():
    assert config.load_toml("bac-x") == {}


def test_load_toml_reads_default_when_present(isolated_config_dir):
    isolated_config_dir.mkdir(parents=True)
    (isolated_config_dir / "bac-x.toml").write_text('[a]\nb = "c"\n', encoding="utf-8")
    assert config.load_toml("bac-x") == {"a": {"b": "c"}}


def test_load_toml_explicit_missing_is_error(tmp_path):
    with pytest.raises(ConfigError, match="does not exist"):
        config.load_toml("bac-x", tmp_path / "nope.toml")


def test_load_toml_invalid_has_detail(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        config.load_toml("bac-x", bad)
    assert info.value.detail


def test_load_env_explicit_missing_is_error(tmp_path):
    with pytest.raises(ConfigError, match="Env file does not exist"):
        config.load_env(tmp_path / ".env")


def test_load_env_explicit_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("BAC_TEST_VALUE", "shell")
    env = tmp_path / ".env"
    env.write_text("BAC_TEST_VALUE=file\n", encoding="utf-8")
    config.load_env(env)
    assert os.environ["BAC_TEST_VALUE"] == "file"


def test_load_env_default_search_starts_at_cwd(tmp_path, monkeypatch):
    project = tmp_path / "project" / "sub"
    project.mkdir(parents=True)
    (tmp_path / "project" / ".env").write_text("BAC_TEST_VALUE=fromcwd\n", encoding="utf-8")
    monkeypatch.chdir(project)
    assert config.load_env() == tmp_path / "project" / ".env"
    assert os.environ["BAC_TEST_VALUE"] == "fromcwd"
    monkeypatch.delenv("BAC_TEST_VALUE")
    monkeypatch.chdir(tmp_path)
    assert config.load_env() is None
    assert "BAC_TEST_VALUE" not in os.environ


def test_pick_precedence(monkeypatch):
    table = {"key": "toml"}
    assert config.pick("BAC_TEST_VALUE", table, "key", "default") == "toml"
    monkeypatch.setenv("BAC_TEST_VALUE", "env")
    assert config.pick("BAC_TEST_VALUE", table, "key", "default") == "env"
    monkeypatch.setenv("BAC_TEST_VALUE", "")
    assert config.pick("BAC_TEST_VALUE", {"key": ""}, "key", "default") == "default"
    assert config.pick(None, {}, "key") is None


def test_require_setup_empty_config():
    with pytest.raises(ConfigError) as info:
        config.require_setup("bac-x", {})
    assert "bac-x --init" in (info.value.detail or "")


def test_require_setup_dotted_keys():
    config.require_setup("bac-x", {"paths": {"target": "/x"}}, "paths.target")
    with pytest.raises(ConfigError, match="paths.target"):
        config.require_setup("bac-x", {"paths": {"target": ""}}, "paths.target")
    with pytest.raises(ConfigError, match="upload.bucket"):
        config.require_setup("bac-x", {"paths": {"target": "/x"}}, "paths.target", "upload.bucket")


def test_write_config_respects_existing(tmp_path):
    target = tmp_path / "deep" / "x.toml"
    assert config.write_config(target, "a = 1\n") is True
    assert config.write_config(target, "a = 2\n") is False
    assert target.read_text(encoding="utf-8") == "a = 1\n"
    assert config.write_config(target, "a = 2\n", overwrite=True) is True
    assert target.read_text(encoding="utf-8") == "a = 2\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_write_env_is_owner_only(tmp_path):
    target = tmp_path / ".env"
    assert config.write_env(target, "KEY=\n") is True
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600
    assert config.write_env(target, "KEY=other\n") is False
    assert target.read_text(encoding="utf-8") == "KEY=\n"


def test_expand(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.expand("~/x") == tmp_path / "x"
