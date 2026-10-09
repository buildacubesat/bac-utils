# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest
from bac_reference_gallery import site
from gallery_testkit import TOOL_DIR, copy_gallery

from bac_common.errors import ConfigError, UsageError

ORDER = [
    "identity-overview",
    "ops-vs-mission",
    "document-family",
    "interface-patterns",
    "data-visualisation",
    "physical-interface",
    "product-sheet",
]


def test_the_checkout_is_found_and_the_order_follows_the_index():
    folder = site.find_site()
    assert folder == TOOL_DIR
    assert [b.name for b in site.boards(folder)] == ORDER


def test_an_unlinked_page_follows_the_linked_ones(tmp_path):
    gallery = copy_gallery(tmp_path / "g")
    (gallery / "examples" / "aaa-extra.html").write_text("<!doctype html><main class='board'></main>")
    names = [b.name for b in site.boards(gallery)]
    assert names == [*ORDER, "aaa-extra"]


def test_source_must_be_a_gallery(tmp_path):
    with pytest.raises(UsageError, match="Not a gallery folder"):
        site.find_site(tmp_path)
    gallery = copy_gallery(tmp_path / "g")
    assert site.find_site(gallery) == gallery.resolve()


def test_missing_pages_point_at_reinstall(monkeypatch, tmp_path):
    monkeypatch.setattr(site, "PACKAGED", tmp_path / "nowhere")
    monkeypatch.setattr(site, "CHECKOUT", tmp_path / "nowhere-either")
    with pytest.raises(ConfigError, match="not found"):
        site.find_site()


def test_select_keeps_gallery_order_and_refuses_unknown_names():
    every = site.boards(TOOL_DIR)
    assert [b.name for b in site.select(every, ["product-sheet", "identity-overview"])] == [
        "identity-overview",
        "product-sheet",
    ]
    assert site.select(every, None) == every
    with pytest.raises(UsageError, match="Unknown board: nope"):
        site.select(every, ["nope", "product-sheet"])


def test_packaged_pages_mirror_the_wheel_layout():
    # pyproject's force-include maps these four names into bac_reference_gallery/pages/
    text = (TOOL_DIR / "pyproject.toml").read_text(encoding="utf-8")
    for name in ("index.html", "css", "assets", "examples"):
        assert f'"{name}" = "bac_reference_gallery/pages/{name}"' in text
    assert site.PACKAGED == Path(site.__file__).resolve().parent / "pages"
