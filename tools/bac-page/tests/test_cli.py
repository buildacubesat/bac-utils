# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

from bac_page import __version__, cli
from bac_page.qr import QrOptions
from bac_page.redirects import parse_renamed, parse_target, write_alias
from page_testkit import git, make_repo, remote_slugs, script_prompts, write_config

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-page"


# -- standard flags and parsing -------------------------------------------------


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_help_lists_the_commands_and_fits():
    r = invoke(cli._main, ["--help"])
    assert r.exit_code == 0
    lines = r.stdout.rstrip().splitlines()
    assert len(lines) <= 24 and max(len(line) for line in lines) <= 80
    for word in ("<url> [slug]", "  list ", "  edit ", "  init ", "Examples:"):
        assert word in r.stdout
    assert "--debug" not in r.stdout


def test_no_command_prints_help_to_stderr_and_exits_2():
    r = invoke(cli._main, [])
    assert r.exit_code == 2 and "usage: bac-page" in r.stderr and r.stdout == ""
    r = invoke(cli._main, ["--qr", "https://x.example"])
    assert r.exit_code == 2


def test_subcommand_help_reaches_the_subcommand():
    r = invoke(cli._main, ["add", "--help"])
    assert r.exit_code == 0 and "usage: bac-page add" in r.stdout and "--size PX" in r.stdout
    r = invoke(cli._main, ["list", "-h"])
    assert r.exit_code == 0 and "--plain" in r.stdout


def test_add_accepts_a_slug_that_starts_with_a_hyphen(tmp_path):
    repo = make_repo(tmp_path)
    write_config(repo)
    r = invoke(cli._main, ["https://x.example", "--", "-dash"])
    assert r.exit_code == 0, r.output
    assert "-dash" in remote_slugs(repo)


def test_add_creates_the_qr_output_directory(tmp_path):
    repo = make_repo(tmp_path)
    write_config(repo)
    out = tmp_path / "new" / "deep"
    r = invoke(cli._main, ["https://x.example", "eps", "--qr", "--output", str(out)])
    assert r.exit_code == 0, r.output
    assert (out / "bac-page-eps.svg").exists()


def test_parse_routes_a_bare_url_to_add():
    command, args = cli.parse(["https://x.example", "eps", "--qr", "--format", "png"])
    assert command == "add" and args.url == "https://x.example" and args.slug == "eps" and args.fmt == "png"
    assert cli.parse(["list", "--plain"])[0] == "list"
    assert cli.parse(["-l"])[0] == "list"
    assert cli.parse(["--init"])[0] == "init"
    assert cli.parse(["edit"])[0] == "edit"


# -- configuration ----------------------------------------------------------------


def test_unconfigured_points_at_init():
    r = invoke(cli._main, ["list"])
    assert r.exit_code == 1
    assert "ERROR bac-page is not set up" in r.stderr and "bac-page --init" in r.stderr and "BAC_PAGE_REPO" in r.stderr


def test_missing_repo_path_names_its_source(tmp_path, monkeypatch):
    write_config(tmp_path / "gone")
    r = invoke(cli._main, ["list"])
    assert r.exit_code == 1 and "does not exist" in r.stderr and "--init" in r.stderr
    monkeypatch.setenv("BAC_PAGE_REPO", str(tmp_path / "also-gone"))
    r = invoke(cli._main, ["list"])
    assert r.exit_code == 1 and "BAC_PAGE_REPO" in r.stderr and "overrides" in r.stderr


def test_env_file_and_no_legacy_env(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ("a", "https://a.example"))
    env = tmp_path / "custom.env"
    env.write_text(f"BAC_PAGE_REPO={repo}\n")
    r = invoke(cli._main, ["--env-file", str(env), "list", "--plain"])
    assert r.exit_code == 0 and r.stdout == "https://bac.page/a\thttps://a.example\n"
    monkeypatch.delenv("BAC_PAGE_REPO", raising=False)
    # 0.6 no longer reads ~/.config/bac-page/.env
    legacy = tmp_path / ".config" / "bac-page" / ".env"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(f"BAC_PAGE_REPO={repo}\n")
    r = invoke(cli._main, ["list", "--plain"])
    assert r.exit_code == 1 and "not set up" in r.stderr
    r = invoke(cli._main, ["--env-file", str(tmp_path / "nope.env"), "list"])
    assert r.exit_code == 1 and "Env file does not exist" in r.stderr


def test_init_writes_the_config_and_rerun_overwrites(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    answers = iter([str(repo), str(repo)])
    monkeypatch.setattr(cli.ui.console, "input", lambda prompt: next(answers))
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0 and "Wrote" in r.stdout
    config = tmp_path / "config" / "bac" / "bac-page.toml"
    assert config.exists() and f'path = "{repo}"' in config.read_text()
    r = invoke(cli._main, ["list", "--plain"])
    assert r.exit_code == 0
    # a second run overwrites; with the variable set it warns about the override
    monkeypatch.setenv("BAC_PAGE_REPO", str(tmp_path))
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0 and "overrides this config" in r.stdout


def test_init_dry_run_and_missing_directory(tmp_path, monkeypatch):
    answers = iter([str(tmp_path / "nowhere"), str(tmp_path)])
    monkeypatch.setattr(cli.ui.console, "input", lambda prompt: next(answers))
    r = invoke(cli._main, ["init"])
    assert r.exit_code == 1 and "Directory does not exist" in r.stderr
    r = invoke(cli._main, ["--init", "--dry-run"])
    assert r.exit_code == 0 and "would write" in r.stdout and "dry run" in r.stdout
    assert "does not look like a git repository" in r.stdout
    assert not (tmp_path / "config" / "bac" / "bac-page.toml").exists()


# -- add --------------------------------------------------------------------------


def test_add_writes_commits_and_pushes(tmp_path):
    repo = make_repo(tmp_path)
    write_config(repo)
    r = invoke(cli._main, ["https://buildacubesat.space/docs/eps", "eps-docs"])
    assert r.exit_code == 0, r.output
    assert "https://bac.page/eps-docs" in r.stdout and "Redirect" in r.stdout
    assert parse_target(repo / "eps-docs" / "index.html") == "https://buildacubesat.space/docs/eps"
    assert git(repo, "log", "-1", "--format=%s") == "add redirect: /eps-docs → https://buildacubesat.space/docs/eps"
    assert git(repo, "status", "--short") == ""
    assert "eps-docs" in remote_slugs(repo)


def test_add_random_slug_and_explicit_add(tmp_path):
    repo = make_repo(tmp_path)
    write_config(repo)
    r = invoke(cli._main, ["add", "https://x.example"])
    assert r.exit_code == 0, r.output
    slugs = remote_slugs(repo)
    assert len(slugs) == 1
    slug = slugs.pop()
    assert len(slug) == 8 and slug.isalnum() and f"https://bac.page/{slug}" in r.stdout


def test_add_dry_run_changes_nothing(tmp_path):
    repo = make_repo(tmp_path)
    write_config(repo)
    r = invoke(cli._main, ["--dry-run", "https://x.example", "eps", "--qr", "--output", str(tmp_path / "q")])
    assert r.exit_code == 0, r.output
    assert "would create" in r.stdout and "would write" in r.stdout and "dry run" in r.stdout
    assert not (repo / "eps").exists() and not (tmp_path / "q").exists()
    assert git(repo, "log", "--oneline").count("\n") == 0


def test_add_refuses_bad_input_before_touching_the_repo(tmp_path):
    repo = make_repo(tmp_path, ("taken", "https://t.example"))
    write_config(repo)
    r = invoke(cli._main, ["not-a-url", "eps"])
    assert r.exit_code == 2 and "must be an http(s) URL" in r.stderr
    r = invoke(cli._main, ["https://x.example", "bad slug"])
    assert r.exit_code == 2 and "Invalid slug" in r.stderr
    r = invoke(cli._main, ["https://x.example", "taken"])
    assert r.exit_code == 1 and "/taken already exists" in r.stderr
    assert git(repo, "status", "--short") == "" and remote_slugs(repo) == {"taken"}


def test_add_with_qr(tmp_path):
    repo = make_repo(tmp_path)
    write_config(repo)
    out = tmp_path / "qr"
    out.mkdir()
    r = invoke(
        cli._main, ["https://x.example", "eps", "--qr", "--format", "png", "--size", "120", "--output", str(out)]
    )
    assert r.exit_code == 0, r.output
    assert (out / "bac-page-eps.png").exists() and "QR code" in r.stdout


def test_git_failure_is_reported_with_detail(tmp_path):
    repo = make_repo(tmp_path)
    write_config(repo)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    r = invoke(cli._main, ["https://x.example", "eps"])
    assert r.exit_code == 1
    assert "ERROR git pull failed." in r.stderr and "not pushed" in r.stderr and "Traceback" not in r.stderr


# -- list -------------------------------------------------------------------------


def test_list_plain_and_empty(tmp_path):
    repo = make_repo(tmp_path, ("b", "https://b.example"), ("A", "https://a.example"))
    write_config(repo)
    r = invoke(cli._main, ["list"])  # not a terminal under invoke: plain lines
    assert r.exit_code == 0
    assert r.stdout == "https://bac.page/A\thttps://a.example\nhttps://bac.page/b\thttps://b.example\n"
    assert invoke(cli._main, ["-l"]).stdout == r.stdout
    empty = make_repo(tmp_path / "e")
    write_config(empty)
    r = invoke(cli._main, ["list", "--plain"])
    assert r.exit_code == 0 and "No redirects" in r.stdout


def test_list_table_in_a_terminal(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ("eps", "https://a.example/[x]"))
    write_config(repo)
    monkeypatch.setattr(type(cli.ui.console), "is_terminal", property(lambda self: True))
    r = invoke(cli._main, ["list"])
    assert r.exit_code == 0
    assert "bac.page redirects (1)" in r.stdout and "/eps" in r.stdout and "https://a.example/[x]" in r.stdout


# -- edit -------------------------------------------------------------------------


def test_edit_changes_the_destination_after_confirmation(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ("eps", "https://old.example"))
    write_config(repo)
    script_prompts(monkeypatch, action="target", text="https://new.example")
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0, r.output
    assert parse_target(repo / "eps" / "index.html") == "https://new.example"
    assert git(repo, "log", "-1", "--format=%s") == "update redirect: /eps → https://new.example"
    assert "eps" in remote_slugs(repo) and git(repo, "status", "--short") == ""


def test_edit_declined_and_dry_run_change_nothing(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ("eps", "https://old.example"))
    write_config(repo)
    script_prompts(monkeypatch, action="target", text="https://new.example", confirm=False)
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0 and "Aborted." in r.stdout
    assert parse_target(repo / "eps" / "index.html") == "https://old.example"
    script_prompts(monkeypatch, action="target", text="https://new.example")
    r = invoke(cli._main, ["edit", "--dry-run"])
    assert r.exit_code == 0 and "dry run" in r.stdout
    assert parse_target(repo / "eps" / "index.html") == "https://old.example"
    script_prompts(monkeypatch, action="cancel")
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0 and "Cancelled." in r.stdout


def test_edit_rename_leaves_an_alias(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ("old", "https://o.example"), ("other", "https://x.example"))
    write_config(repo)
    monkeypatch.setattr(cli, "today", lambda: "2026-10-29")
    script_prompts(monkeypatch, action="slug", text="new")
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0, r.output
    assert parse_target(repo / "new" / "index.html") == "https://o.example"
    assert parse_target(repo / "old" / "index.html") == "https://bac.page/new"
    assert parse_renamed(repo / "old" / "index.html") == ("2026-10-29", "new")
    assert "/old stays as an alias" in r.stdout and "redirects to /new" in r.stdout
    assert git(repo, "log", "-1", "--format=%s") == "rename redirect: /old → /new"
    assert remote_slugs(repo) == {"new", "old", "other"} and git(repo, "status", "--short") == ""
    # a taken name is refused before anything moves
    script_prompts(monkeypatch, action="slug", text="other")
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 1 and "already exists" in r.stderr and (repo / "new").exists()


def test_edit_unchanged_value_does_nothing(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ("eps", "https://o.example"))
    write_config(repo)
    script_prompts(monkeypatch, action="slug")
    assert "Unchanged." in invoke(cli._main, ["edit"]).stdout
    script_prompts(monkeypatch, action="target")
    assert "Unchanged." in invoke(cli._main, ["edit"]).stdout
    assert git(repo, "log", "--oneline").count("\n") == 0


def test_edit_makes_a_qr_code(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ("eps", "https://o.example"))
    write_config(repo)
    out = tmp_path / "qr"
    out.mkdir()
    script_prompts(monkeypatch, action="qr", qr=QrOptions(fmt="svg", output=out))
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0 and (out / "bac-page-eps.svg").exists()
    script_prompts(monkeypatch, action="qr", qr=QrOptions(fmt="png", output=Path(out / "dry")))
    r = invoke(cli._main, ["edit", "--dry-run"])
    assert r.exit_code == 0 and "would write" in r.stdout and not (out / "dry").exists()


def test_edit_with_no_redirects(tmp_path):
    repo = make_repo(tmp_path)
    write_config(repo)
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0 and "No redirects" in r.stdout


# -- renamed slugs (aliases) --------------------------------------------------------


def _aliased_repo(tmp_path):
    """/eps live, /eps-old an alias of it, /x live."""
    repo = make_repo(tmp_path, ("eps", "https://e.example"), ("x", "https://x.example"))
    write_alias(repo, "eps-old", "eps", "2026-10-01")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "alias")
    git(repo, "push", "--quiet")
    write_config(repo)
    return repo


def test_list_marks_aliases_and_old_shows_only_them(tmp_path, monkeypatch):
    _aliased_repo(tmp_path)
    r = invoke(cli._main, ["list", "--plain"])
    assert r.stdout == (
        "https://bac.page/eps\thttps://e.example\n"
        "https://bac.page/eps-old\thttps://bac.page/eps\t2026-10-01\n"
        "https://bac.page/x\thttps://x.example\n"
    )
    r = invoke(cli._main, ["list", "--old", "--plain"])
    assert r.stdout == "https://bac.page/eps-old\thttps://bac.page/eps\t2026-10-01\n"
    monkeypatch.setattr(type(cli.ui.console), "is_terminal", property(lambda self: True))
    r = invoke(cli._main, ["list"])
    assert "redirects (3)" in r.stdout and "→ /eps (renamed 2026-10-01)" in r.stdout
    r = invoke(cli._main, ["list", "--old"])
    assert "renamed slugs (1)" in r.stdout and "/x" not in r.stdout


def test_list_old_with_no_aliases(tmp_path):
    write_config(make_repo(tmp_path, ("a", "https://a.example")))
    r = invoke(cli._main, ["list", "--old"])
    assert r.exit_code == 0 and "No renamed slugs" in r.stdout


def test_add_refuses_an_alias(tmp_path):
    repo = _aliased_repo(tmp_path)
    r = invoke(cli._main, ["https://new.example", "eps-old"])
    assert r.exit_code == 1 and "/eps-old is a renamed slug (now /eps)" in r.stderr
    assert parse_target(repo / "eps-old" / "index.html") == "https://bac.page/eps"


def test_edit_offers_live_slugs_only(tmp_path, monkeypatch):
    _aliased_repo(tmp_path)
    seen = []
    script_prompts(monkeypatch, action="cancel")
    monkeypatch.setattr(cli.prompts, "pick_redirect", lambda redirects: seen.extend(r.slug for r in redirects) or 0)
    invoke(cli._main, ["edit"])
    assert seen == ["eps", "x"]


def test_a_second_rename_points_earlier_aliases_at_the_newest(tmp_path, monkeypatch):
    repo = _aliased_repo(tmp_path)
    monkeypatch.setattr(cli, "today", lambda: "2026-10-29")
    script_prompts(monkeypatch, action="slug", text="eps-docs")  # pick 0 = /eps
    r = invoke(cli._main, ["edit", "--dry-run"])
    assert r.exit_code == 0 and "alias /eps-old (renamed 2026-10-01) now points to /eps-docs" in r.stdout
    assert parse_renamed(repo / "eps-old" / "index.html") == ("2026-10-01", "eps")
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0, r.output
    assert parse_renamed(repo / "eps" / "index.html") == ("2026-10-29", "eps-docs")
    assert parse_renamed(repo / "eps-old" / "index.html") == ("2026-10-01", "eps-docs")  # one hop, date kept
    assert parse_target(repo / "eps-old" / "index.html") == "https://bac.page/eps-docs"
    assert remote_slugs(repo) == {"eps", "eps-docs", "eps-old", "x"} and git(repo, "status", "--short") == ""


def test_renaming_back_onto_an_alias_undoes_the_rename(tmp_path, monkeypatch):
    repo = _aliased_repo(tmp_path)
    monkeypatch.setattr(cli, "today", lambda: "2026-10-29")
    script_prompts(monkeypatch, action="slug", text="eps-old")
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0, r.output
    assert parse_target(repo / "eps-old" / "index.html") == "https://e.example"
    assert parse_renamed(repo / "eps-old" / "index.html") is None
    assert parse_renamed(repo / "eps" / "index.html") == ("2026-10-29", "eps-old")
    assert git(repo, "status", "--short") == ""
    # renaming onto another slug's alias stays refused
    write_alias(repo, "y-old", "x", "2026-10-02")
    script_prompts(monkeypatch, pick=1, action="slug", text="eps")  # /x → /eps, an alias of /eps-old
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 1 and "renamed slug" in r.stderr


def test_undo_with_a_stray_file_and_other_aliases(tmp_path, monkeypatch):
    """a → b → c, then c back onto a: b and c become aliases of a, dates kept; a stray file in /a does not nest."""
    repo = make_repo(tmp_path, ("c", "https://c.example"))
    write_alias(repo, "a", "c", "2026-10-01")
    write_alias(repo, "b", "c", "2026-10-02")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "aliases")
    git(repo, "push", "--quiet")
    (repo / "a" / ".DS_Store").write_text("x")  # untracked
    write_config(repo)
    monkeypatch.setattr(cli, "today", lambda: "2026-10-29")
    script_prompts(monkeypatch, action="slug", text="a")
    r = invoke(cli._main, ["edit", "--dry-run"])
    assert r.exit_code == 0 and "undoes the rename of /a on 2026-10-01" in r.stdout
    assert parse_renamed(repo / "a" / "index.html") == ("2026-10-01", "c")
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 0, r.output
    assert parse_target(repo / "a" / "index.html") == "https://c.example" and not (repo / "a" / "c").exists()
    assert parse_renamed(repo / "b" / "index.html") == ("2026-10-02", "a")
    assert parse_renamed(repo / "c" / "index.html") == ("2026-10-29", "a")
    assert git(repo, "ls-tree", "-r", "--name-only", "origin/main", "a") == "a/index.html"
    assert git(repo, "status", "--short") == ""


def test_rename_onto_a_folder_without_a_redirect_is_refused(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ("x", "https://x.example"))
    (repo / "assets").mkdir()
    write_config(repo)
    script_prompts(monkeypatch, action="slug", text="assets")
    r = invoke(cli._main, ["edit"])
    assert r.exit_code == 1 and "already exists" in r.stderr and (repo / "x" / "index.html").exists()
