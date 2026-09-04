# SPDX-License-Identifier: MIT
from __future__ import annotations

from bac_common import utils
from bac_common.errors import BacError, ConfigError, UsageError, UserAbort


def test_slugify_basic():
    assert utils.slugify("Hello, World!") == "hello-world"
    assert utils.slugify("  spaced   out  ") == "spaced-out"
    assert utils.slugify("Mänu über Zürich") == "manu-uber-zurich"
    assert utils.slugify("Strasse Straße") == "strasse-strasse"
    assert utils.slugify("") == ""
    assert utils.slugify("!!!") == ""


def test_slugify_max_length_on_word_boundary():
    assert utils.slugify("alpha beta gamma delta", max_length=12) == "alpha-beta"
    assert utils.slugify("abcdefghijklmnop", max_length=5) == "abcde"


def test_slugify_separator():
    assert utils.slugify("a b c", separator="_") == "a_b_c"


def test_safe_filename():
    assert utils.safe_filename("report Final (v2).PDF") == "report-final-v2.pdf"
    assert utils.safe_filename("noext", "pdf") == "noext.pdf"
    assert utils.safe_filename("noext", ".PDF") == "noext.pdf"
    assert utils.safe_filename("???", "txt") == "file.txt"
    assert utils.safe_filename("plain") == "plain"


def test_is_kebab():
    assert utils.is_kebab("solar-cell-datasheets")
    assert utils.is_kebab("a1")
    assert not utils.is_kebab("Solar")
    assert not utils.is_kebab("-lead")
    assert not utils.is_kebab("double--hyphen")
    assert not utils.is_kebab("under_score")
    assert not utils.is_kebab("")


def test_hashes(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    assert utils.sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert utils.short_hash("abc") == "ba7816bf"
    assert len(utils.short_hash("abc", 12)) == 12


def test_error_exit_codes_and_detail():
    assert BacError("x").exit_code == 1
    assert ConfigError("x").exit_code == 1
    assert UsageError("x").exit_code == 2
    assert UserAbort().exit_code == 0
    assert str(UserAbort()) == "Aborted."
    err = BacError("Message.", "Detail.")
    assert str(err) == "Message."
    assert err.detail == "Detail."
