# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest
from bac_csr_ingest.errors import ResolverError
from bac_csr_ingest.resolver import InputResolver, is_list_file, split_hint
from bac_csr_ingest.storage import ObjectExists, content_type_for, md5_base64

# -- resolver ----------------------------------------------------------------


def test_list_file_detection(tmp_path):
    (tmp_path / "a.lst").write_text("x\n")
    (tmp_path / "b.txt").write_text("# csr-list\nx\n")
    (tmp_path / "c.md").write_text("# CSR-LIST\nx\n")
    (tmp_path / "d").write_text("# csr-list\n")
    (tmp_path / "e.txt").write_text("just text\n")
    (tmp_path / "f.pdf").write_bytes(b"# csr-list")
    assert is_list_file(tmp_path / "a.lst")
    assert is_list_file(tmp_path / "b.txt")
    assert is_list_file(tmp_path / "c.md")
    assert is_list_file(tmp_path / "d")
    assert not is_list_file(tmp_path / "e.txt")
    assert not is_list_file(tmp_path / "f.pdf")


def test_split_hint():
    assert split_hint("https://a.b/c.pdf :: datasheet from X") == ("https://a.b/c.pdf", "datasheet from X")
    assert split_hint("./x.pdf") == ("./x.pdf", None)
    assert split_hint("x ::") == ("x", None)


def test_list_file_expands_with_hints_and_dedupes(tmp_path, monkeypatch):
    (tmp_path / "one.pdf").write_bytes(b"%PDF")
    (tmp_path / "two.pdf").write_bytes(b"%PDF")
    lst = tmp_path / "in.lst"
    lst.write_text("# comment\none.pdf :: first hint\ntwo.pdf\none.pdf\n\n")
    monkeypatch.chdir(tmp_path)
    items = InputResolver(tmp_path / "tmp").resolve_many([str(lst)], hint="batch")
    assert [Path(i.original).name for i in items] == ["one.pdf", "two.pdf"]
    assert items[0].hint == "first hint" and items[1].hint == "batch"


def test_list_file_self_reference_and_empty_target(tmp_path):
    lst = tmp_path / "in.lst"
    lst.write_text(f"{lst}\n")
    with pytest.raises(ResolverError, match="references itself"):
        InputResolver(tmp_path / "tmp").resolve_many([str(lst)])
    lst.write_text(":: hint only\n")
    with pytest.raises(ResolverError, match="hint without an input"):
        InputResolver(tmp_path / "tmp").resolve_many([str(lst)])


def test_folder_skips_list_files_and_unsupported(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.pdf").write_bytes(b"x")
    (tmp_path / "in" / "b.exe").write_bytes(b"x")
    (tmp_path / "in" / "c.lst").write_text("a.pdf\n")
    notes: list[str] = []
    items = InputResolver(tmp_path / "tmp", notify=notes.append).resolve_many([str(tmp_path / "in")])
    assert [Path(i.original).name for i in items] == ["a.pdf"]
    assert any("Skipping list file" in n for n in notes)


def test_missing_input_is_an_error(tmp_path):
    with pytest.raises(ResolverError, match="does not exist"):
        InputResolver(tmp_path / "tmp").resolve_many([str(tmp_path / "nope.pdf")])


# -- storage -----------------------------------------------------------------


def test_md5_and_content_type(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"abc")
    assert md5_base64(f) == "kAFQmDzST7DWlj99KOF/cg=="
    assert content_type_for("a/b.pdf") == "application/pdf"
    assert content_type_for("a/b.unknownext") == "application/octet-stream"


class _FakeBlob:
    def __init__(self, store: dict, name: str):
        self.store, self.name, self.content_type = store, name, None
        self.md5_hash = store.get(name)

    def upload_from_file(self, f, size, rewind, if_generation_match):
        from google.api_core.exceptions import PreconditionFailed

        assert if_generation_match == 0
        if self.name in self.store:
            raise PreconditionFailed("exists")
        import base64
        import hashlib

        self.store[self.name] = base64.b64encode(hashlib.md5(f.read()).digest()).decode()  # noqa: S324


class _FakeBucket:
    def __init__(self):
        self.store: dict[str, str] = {}

    def blob(self, name):
        return _FakeBlob(self.store, name)

    def get_blob(self, name):
        return _FakeBlob(self.store, name) if name in self.store else None


def test_upload_never_overwrites(tmp_path):
    pytest.importorskip("google.api_core")
    from bac_csr_ingest.storage import GCSUploader

    up = GCSUploader.__new__(GCSUploader)
    up.bucket = _FakeBucket()
    up.public_base_url = "https://cdn"
    a = tmp_path / "a.pdf"
    a.write_bytes(b"content A")
    b = tmp_path / "b.pdf"
    b.write_bytes(b"content B")

    seen: list[int] = []
    assert up.upload(a, "/res/x.pdf", on_progress=seen.append) == "https://cdn/res/x.pdf"
    assert sum(seen) == len(b"content A")
    # Same content again: idempotent, reports full progress, no error.
    seen.clear()
    assert up.upload(a, "res/x.pdf", on_progress=seen.append) == "https://cdn/res/x.pdf"
    assert sum(seen) == len(b"content A")
    # Different content under the same name: refused.
    with pytest.raises(ObjectExists):
        up.upload(b, "res/x.pdf")
    assert up.bucket.store["res/x.pdf"] == md5_base64(a)
