# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from bac_page import redirects as r

from bac_common.errors import BacError, UsageError


def test_redirect_html_round_trips_the_target(tmp_path):
    folder = r.create_redirect(tmp_path, "eps", "https://example.com/eps?x=1&y=2")
    assert folder == tmp_path / "eps"
    text = (folder / "index.html").read_text()
    assert 'content="0; url=https://example.com/eps?x=1&y=2"' in text
    assert "window.location.replace('https://example.com/eps?x=1&y=2')" in text
    assert r.parse_target(folder / "index.html") == "https://example.com/eps?x=1&y=2"


def test_list_skips_dotfolders_cli_and_folders_without_a_redirect(tmp_path):
    r.create_redirect(tmp_path, "Zeta", "https://z.example")
    r.create_redirect(tmp_path, "alpha", "https://a.example")
    r.create_redirect(tmp_path, "cli", "https://nope.example")
    (tmp_path / ".git").mkdir()
    (tmp_path / "plain").mkdir()
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "index.html").write_text("<html></html>")
    assert r.list_redirects(tmp_path) == [
        ("alpha", "https://a.example", None, None),
        ("Zeta", "https://z.example", None, None),
    ]


def test_slug_rules(tmp_path):
    r.validate_slug(tmp_path, "a-B9")
    r.validate_slug(tmp_path, "x" * 24)
    for bad in ("", "has space", "ü", "x" * 25, "a/b"):
        with pytest.raises(UsageError):
            r.validate_slug(tmp_path, bad)
    r.create_redirect(tmp_path, "taken", "https://t.example")
    with pytest.raises(BacError) as exc:
        r.validate_slug(tmp_path, "taken")
    assert exc.value.exit_code == 1 and "already exists" in exc.value.message


def test_target_rules():
    r.validate_target("https://example.com/a?b=c")
    r.validate_target("http://localhost:8000")
    for bad in ("example.com", "ftp://x", "https://has space", ""):
        with pytest.raises(UsageError):
            r.validate_target(bad)


def test_uid_shape():
    uid = r.generate_uid()
    assert len(uid) == 8 and uid.isalnum()
    assert r.short_url(uid) == f"https://bac.page/{uid}"


def test_live_redirect_is_unchanged_and_an_alias_carries_its_marker(tmp_path):
    # the shape every live redirect in the Pages repository has (0.4.2 to 0.6.0)
    assert r.redirect_html("https://example.com/x") == (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta http-equiv="refresh" content="0; url=https://example.com/x">\n'
        '  <link rel="canonical" href="https://example.com/x">\n'
        "  <title>Redirecting…</title>\n"
        "</head>\n"
        "<body>\n"
        '  <p>Redirecting to <a href="https://example.com/x">https://example.com/x</a></p>\n'
        "  <script>window.location.replace('https://example.com/x');</script>\n"
        "</body>\n"
        "</html>\n"
    )
    folder = r.write_alias(tmp_path, "old", "new", "2026-10-29")
    index = folder / "index.html"
    assert '<meta name="bac-page" content="renamed 2026-10-29 to /new">' in index.read_text()
    assert r.parse_target(index) == "https://bac.page/new" and r.parse_renamed(index) == ("2026-10-29", "new")
    (alias,) = r.list_redirects(tmp_path)
    assert alias.is_alias and alias.renamed_to == "new" and alias.renamed_on == "2026-10-29"
    with pytest.raises(BacError) as exc:
        r.validate_slug(tmp_path, "old")
    assert "renamed slug (now /new)" in exc.value.message


def test_a_folder_without_a_redirect_takes_the_slug(tmp_path):
    (tmp_path / "assets").mkdir()
    with pytest.raises(BacError) as exc:
        r.validate_slug(tmp_path, "assets")
    assert "already exists" in exc.value.message
