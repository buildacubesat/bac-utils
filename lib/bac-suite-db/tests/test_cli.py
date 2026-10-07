# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from suite_testkit import write_stub_data

from bac_common import ui
from bac_common.testing import assert_standard_flags, invoke
from bac_suite_db import __version__, schema
from bac_suite_db import cli as cli_mod
from bac_suite_db.cli import _main as main


@pytest.fixture(autouse=True)
def only_the_stub_engine(monkeypatch, stub_engine):
    monkeypatch.setattr(schema, "discover_engines", lambda: [stub_engine.engine])
    return stub_engine


class Answers(list):
    """Feeds ``ui.console.input`` from a list and records the prompts."""

    prompts: list[str]


@pytest.fixture
def answers(monkeypatch):
    queue = Answers()
    queue.prompts = []

    def fake_input(prompt: str = "", **_: object) -> str:
        queue.prompts.append(prompt)
        return queue.pop(0) if queue else ""

    monkeypatch.setattr(ui.console, "input", fake_input)
    return queue


def test_standard_flags():
    assert_standard_flags(main, "bac-db", __version__)


def test_list_engines():
    r = invoke(main, ["-l"])
    assert r.exit_code == 0 and r.stdout.strip() == "stub"


def test_missing_config_points_at_init(tmp_path):
    r = invoke(main, ["--config", str(tmp_path / "none.toml"), "status"])
    assert r.exit_code == 1
    assert "does not exist" in r.stderr


def test_init_writes_config_and_env(tmp_path, answers):
    cfg = tmp_path / "cfg" / "bac-suite.toml"
    data = tmp_path / "ops-data"
    answers += ["postgres", str(data), "postgresql://bac:pw@localhost:5432/bac"]
    r = invoke(main, ["--config", str(cfg), "--init"])
    assert r.exit_code == 0, r.output
    assert cfg.exists() and f'data_dir = "{data}"' in cfg.read_text()
    env = data / ".env"
    assert env.exists() and "BAC_DB_DSN=postgresql://bac:pw@localhost:5432/bac" in env.read_text()
    assert oct(env.stat().st_mode & 0o777) == "0o600"
    assert "pw@" not in r.stdout  # the DSN is never echoed
    # re-running leaves both files alone
    r2 = invoke(main, ["--config", str(cfg), "--init"])
    assert r2.exit_code == 0 and "left as it is" in r2.stdout


def test_init_files_backend_needs_no_dsn(tmp_path, answers):
    cfg = tmp_path / "bac-suite.toml"
    answers += ["files", str(tmp_path / "d")]
    r = invoke(main, ["--config", str(cfg), "--init"])
    assert r.exit_code == 0 and not (tmp_path / "d" / ".env").exists()
    assert "files backend" in r.stdout


def test_init_rejects_an_unknown_backend(tmp_path, answers):
    answers += ["sqlite"]
    r = invoke(main, ["--config", str(tmp_path / "c.toml"), "--init"])
    assert r.exit_code == 2


def test_migrate_dry_run_lists_tables(suite_config):
    r = invoke(main, ["--config", str(suite_config), "migrate", "--dry-run"])
    assert r.exit_code == 0
    assert "stub.rows" in r.stdout and "bac.catalog" in r.stdout and "dry run" in r.stdout


def test_migrate_needs_a_dsn(suite_config):
    r = invoke(main, ["--config", str(suite_config), "migrate"])
    assert r.exit_code == 1 and "BAC_DB_DSN" in r.stderr


def test_migrate_creates_tables(suite_config, fake_conn, monkeypatch):
    monkeypatch.setenv("BAC_DB_DSN", "postgresql://bac:pw@db.example/bac")
    r = invoke(main, ["--config", str(suite_config), "migrate"])
    assert r.exit_code == 0, r.output
    assert set(fake_conn.tables) == {"bac.items", "bac.catalog", "stub.rows"}
    assert "db.example/bac" in r.stdout and "pw" not in r.stdout


def test_status_files_backend(files_config, tmp_path):
    write_stub_data(tmp_path / "data")
    r = invoke(main, ["--config", str(files_config), "status"])
    assert r.exit_code == 0 and "files" in r.stdout and "1/1" in r.stdout


def test_status_db(suite_config, fake_conn, monkeypatch):
    monkeypatch.setenv("BAC_DB_DSN", "postgresql://bac@h/bac")
    schema.migrate(fake_conn, [schema.discover_engines()[0]])
    r = invoke(main, ["--config", str(suite_config), "status"])
    assert r.exit_code == 0, r.output
    assert "bac.items" in r.stdout and "stub.rows" in r.stdout and "stub note" in r.stdout


def test_import_dry_run_validates_and_changes_nothing(suite_config, tmp_path, only_the_stub_engine):
    write_stub_data(tmp_path / "data", rows=4)
    r = invoke(main, ["--config", str(suite_config), "import", "stub", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "rows: 4" in r.stdout and "would replace" in r.stdout and "dry run" in r.stdout
    assert [c[0] for c in only_the_stub_engine.calls] == ["plan"]


def test_import_refuses_bad_data_before_connecting(suite_config, only_the_stub_engine):
    r = invoke(main, ["--config", str(suite_config), "import", "stub"])
    assert r.exit_code == 1 and "stub-rows.csv missing" in r.stderr


def test_import_asks_before_replacing_rows(
    suite_config, tmp_path, fake_conn, monkeypatch, answers, only_the_stub_engine
):
    monkeypatch.setenv("BAC_DB_DSN", "postgresql://bac@h/bac")
    schema.migrate(fake_conn, [only_the_stub_engine.engine])
    write_stub_data(tmp_path / "data", rows=2)
    # first import: tables empty, no question asked
    r = invoke(main, ["--config", str(suite_config), "import", "stub"])
    assert r.exit_code == 0, r.output
    assert len(fake_conn.tables["stub.rows"]) == 2 and not answers.prompts
    # second import: rows exist, the question is asked and declined
    answers += ["n"]
    r = invoke(main, ["--config", str(suite_config), "import", "stub"])
    assert r.exit_code == 0 and "Aborted" in r.stdout
    assert [c[0] for c in only_the_stub_engine.calls].count("import") == 1
    assert "2 rows" in r.stdout
    # --yes skips the question
    write_stub_data(tmp_path / "data", rows=5)
    r = invoke(main, ["--config", str(suite_config), "import", "stub", "--yes"])
    assert r.exit_code == 0 and len(fake_conn.tables["stub.rows"]) == 5


def test_import_explicit_dir(suite_config, tmp_path, fake_conn, monkeypatch):
    monkeypatch.setenv("BAC_DB_DSN", "postgresql://bac@h/bac")
    schema.migrate(fake_conn, schema.discover_engines())
    other = write_stub_data(tmp_path / "other", rows=1).parent
    r = invoke(main, ["--config", str(suite_config), "import", "stub", str(other)])
    assert r.exit_code == 0 and len(fake_conn.tables["stub.rows"]) == 1


def test_export(suite_config, tmp_path, fake_conn, monkeypatch):
    monkeypatch.setenv("BAC_DB_DSN", "postgresql://bac@h/bac")
    schema.migrate(fake_conn, schema.discover_engines())
    fake_conn.execute("INSERT INTO stub.rows (id, note) VALUES (%s,%s)", ("r1", "n"))
    out = tmp_path / "exports" / "today"
    r = invoke(main, ["--config", str(suite_config), "export", "stub", str(out), "--dry-run"])
    assert r.exit_code == 0 and not out.exists() and "would write" in r.stdout
    r = invoke(main, ["--config", str(suite_config), "export", "stub", str(out)])
    assert r.exit_code == 0, r.output
    assert (out / "stub-rows.csv").read_text() == "id,note\nr1,n\n"
    # a second export into the same folder needs --force
    r = invoke(main, ["--config", str(suite_config), "export", "stub", str(out)])
    assert r.exit_code == 2 and "--force" in r.stderr
    r = invoke(main, ["--config", str(suite_config), "export", "stub", str(out), "--force"])
    assert r.exit_code == 0


def test_export_refuses_a_file_as_target(suite_config, tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")
    r = invoke(main, ["--config", str(suite_config), "export", "stub", str(target)])
    assert r.exit_code == 2


def test_unknown_engine_is_a_usage_error(suite_config):
    r = invoke(main, ["--config", str(suite_config), "export", "nope", "out"])
    assert r.exit_code == 2 and "Installed engines: stub" in r.stderr


def test_help_lines_of_subcommands():
    for sub in ("migrate", "status", "import", "export"):
        r = invoke(main, [sub, "--help"])
        assert r.exit_code == 0
        assert len(r.stdout.rstrip().splitlines()) <= 24, sub


def test_run_init_is_importable_by_the_launchers():
    assert callable(cli_mod.run_init)
