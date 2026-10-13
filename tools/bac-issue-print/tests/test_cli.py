# SPDX-License-Identifier: MIT
from __future__ import annotations

from bac_issue_print import __version__, cli
from issue_testkit import comment, load_fixture

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
    assert (
        "\n## Timeline\n\n### user1 commented – 2026-08-31T01:00:00Z\n\nComment 1\n\n---\n\n### user2 commented – "
        in r.stdout
    )
    assert r.stdout.count("\n# ") == 0 and r.stdout.startswith("# ")  # exactly one H1
    assert "—" not in r.stdout  # convention-check: allow A1 – the em dash is what the shell script printed
    assert "Branch" not in r.stdout  # an issue, not a pull request: no /pulls request either
    assert server.urls[0] == "https://codeberg.org/api/v1/repos/buildacubesat-project/bac-hardware/issues/42"
    assert server.urls[1].endswith("/issues/42/timeline?limit=50")
    assert server.tokens == [None, None]  # the issue, the timeline


def test_comments_only_is_the_old_shape(server):
    r = invoke(cli._main, ["hardware", "42", "--comments-only"])
    assert r.exit_code == 0, r.output
    assert "\n## Comments\n\n### user1 – 2026-08-31T01:00:00Z\n\nComment 1\n\n---\n\n### user2 – " in r.stdout
    assert server.urls[1].endswith("/issues/42/comments")  # no page or limit: the endpoint has neither
    server.comments = [comment(n) for n in range(103)]
    r = invoke(cli._main, ["docs", "#7", "--comments-only"])
    assert r.stdout.count("\n### ") == 103 and len(server.urls) == 4  # one request, whatever the length


def test_long_timeline_follows_the_pages(server):
    server.timeline = [comment(n) for n in range(103)]
    r = invoke(cli._main, ["docs", "#7"])
    assert r.exit_code == 0, r.output
    assert r.stdout.count("\n### ") == 103
    assert [u.split("?", 1)[1] for u in server.urls[1:]] == ["limit=50", "limit=50&page=2", "limit=50&page=3"]


def test_null_body_and_empty_timeline(server):
    server.issue = {**server.issue, "body": None, "labels": [], "milestone": None}
    server.comments = []
    r = invoke(cli._main, ["software", "3"])
    assert r.exit_code == 0, r.output
    assert "null" not in r.stdout and "None" not in r.stdout
    assert "Labels" not in r.stdout and "Milestone" not in r.stdout
    assert r.stdout.rstrip().endswith("## Timeline\n\n_Nothing happened after the description._")
    r = invoke(cli._main, ["software", "3", "--comments-only"])
    assert r.stdout.rstrip().endswith("## Comments\n\n_No comments._")


def test_pull_request_154_from_the_real_timeline(server):
    """bac-software #154 as Codeberg served it on 2026-10-13: reviews, pushes, references, a null entry."""
    server.issue = load_fixture("pull-154.json")
    server.timeline = load_fixture("pull-154-timeline.json")
    server.pull = {"head": {"ref": "refactor/csp-addresses"}, "base": {"ref": "main"}}
    server.reviews = [
        {"id": 1912818, "state": "REQUEST_CHANGES", "comments_count": 0},
        {"id": 2076453, "state": "COMMENT", "comments_count": 0},
        {"id": 2104177, "state": "COMMENT", "comments_count": 1},
        {"id": 2104186, "state": "APPROVED", "comments_count": 0},
    ]
    server.review_comments = {
        2104177: [
            {
                "path": "docs/BAC-FSW-SUM-001.md",
                "position": 88,
                "user": {"login": "buildacubesat"},
                "body": "The SBC row still says 4.",
            }
        ]
    }
    r = invoke(cli._main, ["software", "154"])
    assert r.exit_code == 0, r.output
    out = r.stdout
    assert out.startswith(
        "# refactor(shared): move the EPS to CSP address 1 and the SBC to 24 (buildacubesat-project/bac-software #154)\n"
    )
    assert "- State: pull request, open\n" in out and "- Branch: refactor/csp-addresses → main\n" in out
    assert "### Guiimartinho pushed 3 commits – 2026-09-15T03:31:12+02:00\n\n434ae0a, 1977e46, ac1b68a\n" in out
    assert "### Guiimartinho requested a review from buildacubesat – " in out
    assert "### tMAC4k requested changes – 2026-09-27T20:40:54+02:00\n\nThe central EPS/SBC address swap" in out
    assert (
        "### buildacubesat referenced this from issue #159 – fix(large-node/fprime): widen the aliveNodes liveness mask to U64 – "
        in out
    )
    assert "### buildacubesat reviewed – 2026-10-04T14:47:18+02:00\n\nDirection first:" in out
    assert "### Guiimartinho pushed 4 commits – " in out
    assert (
        "### Guiimartinho changed the title – 2026-10-12T04:05:42+02:00\n\nrefactor(shared): move the EPS to CSP address 1 and the SBC to 4 → refactor(shared): move the EPS to CSP address 1 and the SBC to 24\n"
        in out
    )
    assert "### Guiimartinho commented – 2026-10-12T04:05:" in out
    assert (
        "### Guiimartinho referenced this from pull request #155 – fix(small-node): record broadcast as reserved and refuse to send it – "
        in out
    )
    assert (
        "\nhttps://codeberg.org/buildacubesat-project/bac-software/pulls/155#issuecomment-25119447\n\n> @tMAC4k @buildacubesat both reviews are in"
        in out
    )
    assert "### Guiimartinho referenced this from pull request #162 – " in out
    assert (
        "### buildacubesat reviewed – 2026-10-13T17:51:16+02:00\n\n(edit: added the comment in-line, see below)\n\n**`docs/BAC-FSW-SUM-001.md` line 88**\n\nThe SBC row still says 4.\n"
        in out
    )
    assert "### buildacubesat approved – 2026-10-13T18:07:28+02:00\n\nThanks Gui!" in out
    assert out.count("\n### ") == 19  # 20 entries, one null skipped
    assert "1 timeline entry the server could not serialise, skipped" in r.stderr
    assert "null" not in out and "None" not in out
    reviews_url = [u for u in server.urls if u.endswith("/pulls/154/reviews?limit=50")]
    assert len(reviews_url) == 1 and sum("/reviews/2104177/comments" in u for u in server.urls) == 1


def test_review_shells_and_other_events():
    from bac_issue_print.timeline import build_entries

    tl = [
        {"type": "review", "user": {"login": "a"}, "created_at": "t", "body": "", "review_id": 1},
        {"type": "review", "user": {"login": "a"}, "created_at": "t", "body": "", "review_id": 2},
        {"type": "label", "user": {"login": "a"}, "created_at": "t", "body": "1", "label": {"name": "bug"}},
        {"type": "label", "user": {"login": "a"}, "created_at": "t", "body": "", "label": {"name": "bug"}},
        {"type": "close", "user": {"login": "a"}, "created_at": "t", "body": ""},
        {"type": "assignees", "user": {"login": "a"}, "created_at": "t", "assignee": {"login": "b"}},
        {"type": "milestone", "user": {"login": "a"}, "created_at": "t", "milestone": {"title": "R2"}},
        {"type": "review_request", "user": {"login": "a"}, "created_at": "t", "removed_assignee": {"login": "b"}},
        {"type": "something_new", "user": {"login": "a"}, "created_at": "t", "body": "x"},
        {"type": "pull_push", "user": {"login": "a"}, "created_at": "t", "body": "not json"},
    ]
    entries, skipped = build_entries(tl, {1: {"state": "COMMENT"}, 2: {"state": "APPROVED"}}, {})
    assert skipped == 0
    assert [e.verb for e in entries] == [
        "approved",  # the empty COMMENT review shell is dropped, the approval stays
        "added the label bug",
        "removed the label bug",
        "closed this",
        "assigned b",
        "set the milestone to R2",
        "removed the review request for b",
        "something new",
        "pushed 0 commits",
    ]


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
