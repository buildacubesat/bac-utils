# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest
from bac_update_content_plan import __version__, cli
from bac_update_content_plan.cli import TOOL, _main, run_init
from contentplan_testkit import SHEET_ID, FakeClient, git, install_fake_client, make_repo, write_setup

from bac_common.errors import ExternalToolError
from bac_common.testing import assert_standard_flags, invoke


def test_standard_flags():
    assert_standard_flags(_main, TOOL, __version__)


def test_unconfigured_points_at_init(tmp_path):
    result = invoke(_main, ["--config", str(tmp_path / "none.toml")])
    assert result.exit_code == 1
    assert "does not exist" in result.stderr
    result = invoke(_main, [])  # default path, missing file → empty config
    assert result.exit_code == 1
    assert "--init" in result.stderr


def test_missing_key_is_reported_before_fetching(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    config, key = write_setup(tmp_path, repo)
    key.unlink()
    client = install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config)])
    assert result.exit_code == 1
    assert "key not found" in result.stderr
    assert "set by [credentials] file" in result.stderr
    assert client.calls == []


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    config, _ = write_setup(tmp_path, repo)
    client = install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert client.calls == [(SHEET_ID, "'Content Plan'!A:D")]
    assert not (repo / "content" / "content-plan.md").exists()
    assert "Would write" in result.stdout
    assert "dry run" in result.stdout
    assert "Rows in sheet" in result.stdout and "3" in result.stdout
    assert "1 row without a 'Status' value" in result.stdout


def test_write_without_commit(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    config, _ = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config)])
    assert result.exit_code == 0, result.output
    text = (repo / "content" / "content-plan.md").read_text(encoding="utf-8")
    assert "| EPS walkthrough | YouTube | published |  |" in text
    assert "Committed" not in result.stdout
    assert git(repo, "status", "--porcelain") == "?? content/"


def test_commit_then_unchanged(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    config, _ = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--commit", "-m", "Plan: week 41"])
    assert result.exit_code == 0, result.output
    assert "Committed" in result.stdout
    assert git(repo, "log", "-1", "--format=%s") == "Plan: week 41"
    assert git(repo, "status", "--porcelain") == ""

    again = invoke(_main, ["--config", str(config), "--commit"])
    assert again.exit_code == 0, again.output
    assert "(unchanged)" in again.stdout
    assert "Nothing to commit" in again.stdout
    assert "none" in again.stdout  # Lines changed
    assert git(repo, "rev-list", "--count", "HEAD") == "2"


def test_commit_leaves_other_staged_changes_alone(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    (repo / "other.txt").write_text("staged by hand\n", encoding="utf-8")
    git(repo, "add", "other.txt")
    config, _ = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--commit"])
    assert result.exit_code == 0, result.output
    assert git(repo, "show", "--stat", "--format=", "HEAD").count("|") == 1
    assert "content/content-plan.md" in git(repo, "show", "--stat", "--format=", "HEAD")
    assert git(repo, "status", "--porcelain") == "A  other.txt"


def test_dry_run_compares_against_the_configured_branch(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "--quiet", "-b", "content")
    (repo / "content").mkdir()
    (repo / "content" / "content-plan.md").write_text("# Content Plan\n\nold\n", encoding="utf-8")
    git(repo, "add", "content")
    git(repo, "commit", "--quiet", "-m", "plan on content")
    git(repo, "checkout", "--quiet", "main")
    config, _ = write_setup(tmp_path, repo, branch="content")
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--commit", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Would check out content" in result.stdout
    assert "+5 −1" in result.stdout  # against the file on `content` (3 lines), not the missing one on main


def test_failed_push_still_prints_the_summary(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "remote", "add", "origin", str(tmp_path / "missing.git"))
    config, _ = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--push", "-y"])
    assert result.exit_code == 1
    assert "git push failed" in result.stderr
    assert "Pushed" in result.stdout and "failed" in result.stdout
    assert git(repo, "log", "-1", "--format=%s") == "Update content plan"


def test_push_with_yes(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, with_remote=True)
    config, _ = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--push", "-y"])
    assert result.exit_code == 0, result.output
    assert "Pushed origin/main" in result.stdout
    assert git(repo, "rev-parse", "HEAD") == git(repo, "rev-parse", "origin/main")


def test_push_without_terminal_is_skipped(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, with_remote=True)
    config, _ = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient())
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    result = invoke(_main, ["--config", str(config), "--push"])
    assert result.exit_code == 0, result.output
    assert "Push skipped" in result.stdout
    assert "-y" in result.stdout
    assert git(repo, "rev-parse", "HEAD") != git(repo, "rev-parse", "origin/main")


def test_push_answered_no(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, with_remote=True)
    config, _ = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient())
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.ui.console, "input", lambda prompt: "n")
    result = invoke(_main, ["--config", str(config), "--push"])
    assert result.exit_code == 0, result.output
    assert "Push skipped" in result.stdout


def test_repo_checked_before_fetch(tmp_path, monkeypatch):
    config, _ = write_setup(tmp_path, tmp_path / "not-a-repo")
    client = install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--commit"])
    assert result.exit_code == 1
    assert "Repository does not exist" in result.stderr
    assert client.calls == []
    # Without --commit too: a typo in output.repo must not become a new directory tree.
    result = invoke(_main, ["--config", str(config)])
    assert result.exit_code == 1
    assert client.calls == []
    assert not (tmp_path / "not-a-repo").exists()

    plain = tmp_path / "plain"
    plain.mkdir()
    config, _ = write_setup(tmp_path, plain)
    result = invoke(_main, ["--config", str(config), "--commit"])
    assert result.exit_code == 1
    assert "Not a git work tree" in result.stderr
    assert client.calls == []


def test_missing_branch_is_a_config_error(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    config, _ = write_setup(tmp_path, repo, branch="content")
    client = install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--commit"])
    assert result.exit_code == 1
    assert "Branch 'content' does not exist" in result.stderr
    assert client.calls == []


def test_switches_branch_before_writing(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "branch", "content")
    config, _ = write_setup(tmp_path, repo, branch="content")
    install_fake_client(monkeypatch, FakeClient())
    dry = invoke(_main, ["--config", str(config), "--commit", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "Would check out content" in dry.stdout
    assert git(repo, "symbolic-ref", "--short", "HEAD") == "main"

    result = invoke(_main, ["--config", str(config), "--commit"])
    assert result.exit_code == 0, result.output
    assert "Checked out content (was main)" in result.stdout
    assert git(repo, "symbolic-ref", "--short", "HEAD") == "content"
    assert git(repo, "log", "-1", "--format=%s") == "Update content plan"


def test_dirty_checkout_fails_before_writing(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "branch", "content")
    (repo / "README.md").write_text("# edited\n", encoding="utf-8")
    git(repo, "checkout", "--quiet", "content")
    (repo / "README.md").write_text("# other\n", encoding="utf-8")
    git(repo, "commit", "--quiet", "-am", "diverge")
    git(repo, "checkout", "--quiet", "main")
    (repo / "README.md").write_text("# dirty\n", encoding="utf-8")
    config, _ = write_setup(tmp_path, repo, branch="content")
    client = install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--commit"])
    assert result.exit_code == 1
    assert "git checkout failed" in result.stderr
    assert client.calls == []
    assert not (repo / "content").exists()


def test_sheet_error_is_reported(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    config, _ = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient(error=ExternalToolError("Google Sheets refused (HTTP 403).", "Share")))
    result = invoke(_main, ["--config", str(config)])
    assert result.exit_code == 1
    assert "HTTP 403" in result.stderr
    assert not (repo / "content").exists()


def test_env_var_overrides_configured_key(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    config, _ = write_setup(tmp_path, repo, credentials=str(tmp_path / "gone.json"))
    key = tmp_path / "env-key.json"
    key.write_text("{}", encoding="utf-8")
    (tmp_path / ".env").write_text(f"BAC_GCP_CREDENTIALS={key}\n", encoding="utf-8")
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--dry-run", "--env-file", str(tmp_path / ".env")])
    assert result.exit_code == 0, result.output


def test_init_writes_answers(tmp_path):
    target = tmp_path / "cfg" / "bac-update-content-plan.toml"
    answers = iter([f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0", "~/bac/bac-docs", "", "main"])
    asked: list[tuple[str, str]] = []

    def ask(question: str, default: str) -> str:
        asked.append((question, default))
        return next(answers) or default

    assert run_init(str(target), ask) == 0
    text = target.read_text(encoding="utf-8")
    assert f'id = "{SHEET_ID}"' in text
    assert 'repo = "~/bac/bac-docs"' in text
    assert 'file = "content/content-plan.md"' in text
    assert [q for q, _ in asked][:2] == ["Spreadsheet id or URL", "Docs repository (git work tree)"]
    # Re-running leaves the file alone.
    before = target.read_text(encoding="utf-8")
    assert run_init(str(target), lambda q, d: "changed") == 0
    assert target.read_text(encoding="utf-8") == before


def test_init_without_terminal_writes_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    config = tmp_path / "x.toml"
    result = invoke(_main, ["--init", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert 'id = ""' in config.read_text(encoding="utf-8")
    assert "fill in [sheet] id" in result.stdout
    assert "BAC_GCP_CREDENTIALS" in result.stdout


def test_init_rejects_a_bad_sheet(tmp_path):
    with pytest.raises(Exception, match="Not a Google Sheets"):
        run_init(str(tmp_path / "x.toml"), lambda q, d: "content plan" if "Spreadsheet" in q else d)
    assert not (tmp_path / "x.toml").exists()


def test_module_entry_point(tmp_path, monkeypatch):
    import runpy

    monkeypatch.setattr("sys.argv", ["bac-update-content-plan", "--config", str(tmp_path / "none.toml")])
    with pytest.raises(SystemExit) as info:
        runpy.run_module("bac_update_content_plan", run_name="__main__", alter_sys=True)
    assert info.value.code == 1


def test_help_fits_on_python_311_too():
    """The ``--config`` help wraps because the tool name is long; the budget holds with margin."""
    result = invoke(_main, ["--help"])
    assert len(result.stdout.rstrip("\n").splitlines()) <= 23


@pytest.mark.parametrize("argv", [["--message"], ["--config"], ["--bogus"]])
def test_bad_arguments_exit_2(argv):
    assert invoke(_main, argv).exit_code == 2


def test_target_outside_repo_is_refused(tmp_path: Path, monkeypatch):
    repo = make_repo(tmp_path)
    config, _ = write_setup(tmp_path, repo, file="../escape.md")
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config)])
    assert result.exit_code == 1
    assert "relative path inside" in result.stderr


def test_the_opening_names_where_the_key_path_came_from(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    config, key = write_setup(tmp_path, repo)
    install_fake_client(monkeypatch, FakeClient())
    result = invoke(_main, ["--config", str(config), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "([credentials] file)" in result.stdout
    monkeypatch.setenv("BAC_GCP_CREDENTIALS", str(key))
    result = invoke(_main, ["--config", str(config), "--dry-run"])
    assert "(BAC_GCP_CREDENTIALS)" in result.stdout
