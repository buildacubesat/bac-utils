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
    assert r.list_redirects(tmp_path) == [("alpha", "https://a.example"), ("Zeta", "https://z.example")]


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
