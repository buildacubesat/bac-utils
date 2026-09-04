# SPDX-License-Identifier: MIT
from __future__ import annotations

from bac_issue_print import __version__, cli
from bac_issue_print.api import PAGE_SIZE
from issue_testkit import comment

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-issue-print"


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_list_defaults_without_config():
    r = invoke(cli._main, ["-l"])
    assert r.exit_code == 0, r.output
    assert "hardware     buildacubesat-project/bac-hardware" in r.stdout
    assert len(r.stdout.splitlines()) == 4


def test_prints_markdown(server):
    r = invoke(cli._main, ["hardware", "42"])
    assert r.exit_code == 0, r.output
    assert r.stdout.startswith("# Watchdog resets the MCU (buildacubesat-project/bac-hardware #42)\n\n- Author: mnu\n")
    assert "- Labels: bug, eps\n- Milestone: R2\n- URL: https://codeberg.org/" in r.stdout
    assert "\n## Comments\n\n### user1 – 2026-08-31T01:00:00Z\n\nComment 1\n\n---\n\n### user2 – " in r.stdout
    assert r.stdout.count("\n# ") == 0 and r.stdout.startswith("# ")  # exactly one H1
    assert "—" not in r.stdout  # convention-check: allow A1 – the em dash is what the shell script printed
    assert server.urls[0] == "https://codeberg.org/api/v1/repos/buildacubesat-project/bac-hardware/issues/42"
    assert server.urls[1].endswith("/issues/42/comments?page=1&limit=50")
    assert server.tokens == [None, None, None]  # issue, first page, the empty page that ends the walk


def test_paginates_comments(server):
    server.comments = [comment(n) for n in range(PAGE_SIZE * 2 + 3)]
    r = invoke(cli._main, ["docs", "#7"])
    assert r.exit_code == 0, r.output
    assert r.stdout.count("\n### ") == PAGE_SIZE * 2 + 3
    assert [u.split("?")[1] for u in server.urls[1:]] == [f"page={n}&limit=50" for n in (1, 2, 3, 4)]

    server.urls.clear()
    server.comments = [comment(n) for n in range(PAGE_SIZE * 2)]  # exact multiple: one extra, empty page
    r = invoke(cli._main, ["docs", "7"])
    assert r.stdout.count("\n### ") == PAGE_SIZE * 2 and len(server.urls) == 1 + 3


def test_paginates_on_a_server_with_a_smaller_cap(server):
    server.comments = [comment(n) for n in range(45)]
    server.cap = 20  # the server ignores limit=50 and pages by 20
    r = invoke(cli._main, ["docs", "7"])
    assert r.exit_code == 0, r.output
    assert r.stdout.count("\n### ") == 45 and len(server.urls) == 1 + 3 + 1


def test_null_body_and_no_comments(server):
    server.issue = {**server.issue, "body": None, "labels": [], "milestone": None}
    server.comments = []
    r = invoke(cli._main, ["software", "3"])
    assert r.exit_code == 0, r.output
    assert "null" not in r.stdout and "None" not in r.stdout
    assert "Labels" not in r.stdout and "Milestone" not in r.stdout
    assert r.stdout.rstrip().endswith("## Comments\n\n_No comments._")


def test_owner_slash_repo_and_token(server, monkeypatch):
    monkeypatch.setenv("CODEBERG_TOKEN", "abc123")
    r = invoke(cli._main, ["someone/their-repo", "1"])
    assert r.exit_code == 0, r.output
    assert server.urls[0].endswith("/repos/someone/their-repo/issues/1")
    assert set(server.tokens) == {"abc123"}


def test_env_file_provides_token(server, tmp_path):
    env = tmp_path / "secrets.env"
    env.write_text("CODEBERG_TOKEN=fromfile\n", encoding="utf-8")  # convention-check: allow H1
    r = invoke(cli._main, ["--env-file", str(env), "hardware", "42"])
    assert r.exit_code == 0, r.output
    assert server.tokens[0] == "fromfile"


def test_dotenv_in_working_directory_provides_token(server, tmp_path):
    (tmp_path / ".env").write_text("CODEBERG_TOKEN=fromcwd\n", encoding="utf-8")  # convention-check: allow H1
    r = invoke(cli._main, ["hardware", "42"])
    assert r.exit_code == 0, r.output
    assert server.tokens[0] == "fromcwd"


def test_usage_errors(server):
    for argv in (["hardware"], [], ["hardware", "x"], ["hardware", "0"], ["nope", "1"], ["a/b/c", "1"]):
        r = invoke(cli._main, argv)
        assert r.exit_code == 2, argv
        assert "Traceback" not in r.stderr
    assert server.urls == []
    r = invoke(cli._main, ["nope", "1"])
    assert "Unknown repository key" in r.stderr and "-l" in r.stderr


def test_http_error_is_clean(server):
    server.status = 404
    r = invoke(cli._main, ["hardware", "999"])
    assert r.exit_code == 1
    assert r.stdout == ""
    assert r.stderr.startswith("ERROR HTTP 404 from codeberg.org\n")
    assert "bac-hardware/issues/999" in r.stderr and "Traceback" not in r.stderr


def test_init_and_config(server, tmp_path):
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0, r.output
    path = tmp_path / "config" / "bac" / "bac-issue-print.toml"
    assert path.exists() and "✓ Wrote" in r.stdout
    r = invoke(cli._main, ["--init"])
    assert "exists; left unchanged" in r.stdout

    path.write_text('host = "https://git.example.org"\nowner = "acme"\n\n[repos]\nfw = "firmware"\n', encoding="utf-8")
    r = invoke(cli._main, ["-l"])
    assert r.stdout.strip() == "fw           acme/firmware"
    r = invoke(cli._main, ["fw", "5"])
    assert r.exit_code == 0, r.output
    assert server.urls[0] == "https://git.example.org/api/v1/repos/acme/firmware/issues/5"

    path.write_text("[repos]\nfw = 5\n", encoding="utf-8")
    r = invoke(cli._main, ["fw", "5"])
    assert r.exit_code == 1 and "[repos] must map keys" in r.stderr
