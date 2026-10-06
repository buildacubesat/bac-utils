# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from bac_kicad_generate_artifacts.qr import (
    QrError,
    find_markers,
    insert_qr,
    insert_qr_file,
    qr_matrix,
    substitute_variables,
)
from genart_testkit import DSW, SYNTH

from bac_common import sexp

BOARD = SYNTH / "bac-synth-v2.kicad_pcb"


def _rects(root: sexp.Node, layer: str) -> list[sexp.Node]:
    return [
        r for r in root.children("gr_rect") if r.child("layer").value(1) == layer and r.child("fill").value(1) == "yes"
    ]


def _xy(node: sexp.Node, head: str) -> tuple[float, float]:
    c = node.child(head)
    return float(c.value(1)), float(c.value(2))


def test_matrix_is_square_and_grows_with_the_data():
    small = qr_matrix("bac.page/x")  # 10 bytes fit version 1
    assert len(small) == 21 and all(len(row) == 21 for row in small)
    assert small[0][:7] == [True] * 7  # finder pattern, no quiet zone
    assert len(qr_matrix("https://bac.page/synth?board=bac-eps-synth-v2r3&serial=0001")) > 21


def test_find_markers():
    text, root = sexp.parse_file(BOARD)
    found = find_markers(text, root, "QR_MARKER")
    assert [(p.layer, p.back) for p in found] == [("F.SilkS", False), ("B.SilkS", True)]
    assert (found[0].x0, found[0].y0, found[0].side) == (140.0, 105.0, 10.0)
    assert found[0].indent == "\t"
    assert find_markers(text, root, "NOT_A_MARKER")[0].side == 4.0
    assert find_markers(text, root, "nothing") == []


def test_rectangular_box_uses_the_centred_square():
    text = '(kicad_pcb (version 20241229)\n\t(gr_text_box "M"\n\t\t(start 10 10)\n\t\t(end 30 20)\n\t\t(layer "F.SilkS")\n\t)\n)\n'
    p = find_markers(text, sexp.parse(text), "M")[0]
    assert (p.x0, p.y0, p.side) == (15.0, 10.0, 10.0)


def test_rotated_box_with_pts():
    text = '(kicad_pcb\n\t(gr_text_box "M"\n\t\t(pts (xy 0 0) (xy 8 0) (xy 8 8) (xy 0 8))\n\t\t(layer "B.Cu")\n\t)\n)\n'
    p = find_markers(text, sexp.parse(text), "M")[0]
    assert (p.x0, p.y0, p.side, p.back) == (0.0, 0.0, 8.0, True)


def test_insert_replaces_only_the_markers_and_keeps_the_rest_byte_for_byte():
    text, root = sexp.parse_file(BOARD)
    new, count, smallest = insert_qr(text, root, "QR_MARKER", "https://bac.page/synth")
    assert count == 2 and smallest == pytest.approx(0.4)
    new_root = sexp.parse(new)
    assert len(new_root.children("gr_text_box")) == 1  # NOT_A_MARKER stays
    assert len(new_root.children("footprint")) == 2
    # everything before the first marker and after the last one is unchanged
    first, last = find_markers(text, root, "QR_MARKER")[0], find_markers(text, root, "QR_MARKER")[-1]
    assert new.startswith(text[: first.start]) and new.endswith(text[last.end :])
    matrix = qr_matrix("https://bac.page/synth")
    dark = sum(sum(row) for row in matrix)
    front, back = _rects(new_root, "F.SilkS"), _rects(new_root, "B.SilkS")
    assert len(front) == len(back) == dark
    module = 10 / len(matrix)
    # the first dark module of the first row sits at the box's top-left corner on the front …
    assert min(_xy(r, "start") for r in front) == (140.0, 105.0)
    assert max(_xy(r, "end")[0] for r in front) == pytest.approx(150.0)
    # … and the back is mirrored left-right: the same module ends at the right edge
    back_row0 = sorted(_xy(r, "start") for r in back if _xy(r, "start")[1] == 118.0)
    front_row0 = sorted(_xy(r, "start") for r in front if _xy(r, "start")[1] == 105.0)
    mirrored = sorted((150.0 - module - (x - 140.0), 118.0) for x, _ in front_row0)
    assert [pytest.approx(b[0]) for b in back_row0] == [m[0] for m in mirrored]
    # rectangles are filled, zero-width, with fresh uuids, in KiCad's own indentation
    sample = front[0]
    assert sample.child("stroke").child("width").value(1) == "0"
    assert len({r.child("uuid").value(1) for r in front + back}) == 2 * dark
    assert "\n\t(gr_rect\n\t\t(start 140 105)\n\t\t(end 140.4 105.4)\n" in new


def test_fill_token_follows_the_file_version():
    text = '(kicad_pcb (version 20240108)\n\t(gr_text_box "M"\n\t\t(start 0 0)\n\t\t(end 4 4)\n\t\t(layer "F.SilkS")\n\t)\n)\n'
    new, _, _ = insert_qr(text, sexp.parse(text), "M", "x")
    assert "(fill solid)" in new and "(fill yes)" not in new


def test_no_marker_is_an_error():
    text, root = sexp.parse_file(BOARD)
    with pytest.raises(QrError, match="No MISSING text box"):
        insert_qr(text, root, "MISSING", "x")


def test_rotated_marker_is_an_error():
    text = '(kicad_pcb\n\t(gr_text_box "M"\n\t\t(start 0 0)\n\t\t(end 4 4)\n\t\t(angle 90)\n\t\t(layer "F.SilkS")\n\t)\n)\n'
    with pytest.raises(QrError, match="rotated by 90"):
        find_markers(text, sexp.parse(text), "M")
    text = text.replace("(angle 90)", "(angle 180)")
    assert len(find_markers(text, sexp.parse(text), "M")) == 1


def test_marker_without_geometry_is_an_error():
    text = '(kicad_pcb\n\t(gr_text_box "M"\n\t\t(layer "F.SilkS")\n\t)\n)\n'
    with pytest.raises(QrError, match="corners"):
        find_markers(text, sexp.parse(text), "M")


def test_variables():
    assert (
        substitute_variables("${COMMENT4}/${REVISION}", {"COMMENT4": "https://bac.page/x", "REVISION": "2"})
        == "https://bac.page/x/2"
    )
    assert substitute_variables("${UNKNOWN} stays", {}) == "${UNKNOWN} stays"


def test_insert_in_file_keeps_line_endings(tmp_path: Path):
    src = tmp_path / "crlf.kicad_pcb"
    src.write_bytes(BOARD.read_bytes().replace(b"\n", b"\r\n"))
    assert insert_qr_file(src, "QR_MARKER", "x")[0] == 2
    data = src.read_bytes()
    assert b"\r\n" in data and data.count(b"\n") == data.count(b"\r\n")


def test_deployment_switch_marker(tmp_path: Path):
    board = tmp_path / "dsw.kicad_pcb"
    shutil.copy(DSW / "bac-deployment-switch-v1.kicad_pcb", board)
    text, root = sexp.parse_file(board)
    (p,) = find_markers(text, root, "QR_MARKER")
    assert p.layer == "B.SilkS" and p.side == pytest.approx(3.2)
    count, module = insert_qr_file(board, "QR_MARKER", "https://bac.page/dsw-v1")
    assert count == 1 and module == pytest.approx(3.2 / 25)  # a 25-module code in 3.2 mm
    new_root = sexp.parse(board.read_text(encoding="utf-8"))
    assert new_root.children("gr_text_box") == [] and len(_rects(new_root, "B.SilkS")) > 200
    assert len(new_root.children("footprint")) == 2
