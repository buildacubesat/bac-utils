# SPDX-License-Identifier: MIT
"""Geometry, validity, placement and the edits on the small test board."""

from __future__ import annotations

import math

import pytest
from bac_kicad_stitch.board import read_board
from bac_kicad_stitch.config import Settings, pitch_from_frequency, validate
from bac_kicad_stitch.edit import insert_vias, remove_vias
from bac_kicad_stitch.geometry import Transform, arc_points
from bac_kicad_stitch.stitch import as_vias, masks, plan
from stitch_testkit import BOARD

from bac_common.errors import ConfigError
from bac_common.sexp import parse


def board(settings: Settings | None = None):
    root = parse(BOARD)
    return BOARD, root, read_board(root, (settings or Settings()).net)


def test_transform_rotates_counter_clockwise_on_screen():
    # y points down in a board file: a +90° rotation turns +x into -y
    x, y = Transform(10, 10, 90).point(1, 0)
    assert (round(x, 6), round(y, 6)) == (10, 9)


def test_arc_points_follow_the_mid_point():
    pts = arc_points((0, 0), (1, 1), (2, 0))
    assert pts[0] == (0, 0) and pts[-1] == (2, 0)
    assert max(y for _, y in pts) == pytest.approx(1, abs=0.01)
    assert all(math.hypot(x - 1, y) == pytest.approx(1, abs=1e-9) for x, y in pts)


def test_board_model():
    _, _, b = board()
    assert b.copper_layers == ["F.Cu", "B.Cu"]
    assert b.outline.area == pytest.approx(600)
    assert b.epsilon_r == 4.0
    assert [v.net for v in b.ground_vias] == ["GND"]
    assert not b.ground_fill["F.Cu"].is_empty and not b.ground_fill["B.Cu"].is_empty
    assert b.other_copper["B.Cu"].area > 0  # the track
    assert len(b.footprints) == 1
    fp = b.footprints[0]
    assert fp.reference == "U1" and fp.pads == 4 and fp.min_pad_pitch == pytest.approx(0.5)
    assert fp.is_fine_pitch(0.65, 4) and not fp.is_fine_pitch(0.65, 6)
    # the rotated courtyard: 2 mm wide, 3 mm tall around (22, 14)
    minx, miny, maxx, maxy = fp.courtyard.bounds
    assert (round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)) == (21, 12.5, 23, 15.5)


def test_masks_respect_edge_track_island_and_courtyard():
    s = Settings(fine_pitch_pads=4, step=0.1)
    _, _, b = board(s)
    gx, gy, target, valid, avoided = masks(b, s)
    assert avoided == ["U1"]
    target, valid = target.reshape(gx.shape), valid.reshape(gx.shape)

    def at(x: float, y: float) -> tuple[bool, bool]:
        i = int(round((y - gy[0, 0]) / s.step))
        j = int(round((x - gx[0, 0]) / s.step))
        return bool(target[i, j]), bool(valid[i, j])

    assert at(15, 5) == (True, True)
    assert at(0.5, 5) == (False, False)  # outside the fill and inside the edge clearance
    assert at(15, 15) == (True, False)  # the SIG track on B.Cu
    assert at(10, 10) == (False, False)  # the island cut out of the fill
    assert at(22, 14) == (True, False)  # the fine-pitch courtyard
    assert at(22, 14) != (True, True)


def test_plan_covers_the_board_and_is_deterministic():
    s = Settings(pitch=6, fine_pitch_pads=4)
    _, _, b = board(s)
    r1 = plan(b, s)
    r2 = plan(b, s)
    assert r1.placed == r2.placed
    assert r1.existing == 1 and r1.placed
    assert r1.coverage_after == pytest.approx(1.0) and r1.gaps == []
    assert r1.coverage_before < r1.coverage_after
    for p in r1.placed:
        assert 0.5 + 0.3 <= p.x <= 29.2 and 0.8 <= p.y <= 19.2


def test_existing_vias_count_and_the_second_run_adds_nothing():
    s = Settings(pitch=6, fine_pitch_pads=4)
    text, root, b = board(s)
    result = plan(b, s)
    stitched, uuids = insert_vias(text, root, as_vias(result, s))
    assert len(uuids) == len(result.placed) == stitched.count('(net "GND")') - 2  # the zone and the first via
    assert stitched.count("\t(via\n") == 1 + len(result.placed)
    assert '(group "bac-stitch"' in stitched
    root2 = parse(stitched)
    b2 = read_board(root2, "GND")
    assert len(b2.ground_vias) == 1 + len(result.placed)
    assert sum(v.stitched for v in b2.vias) == len(result.placed)
    again = plan(b2, s)
    assert again.placed == []
    assert again.coverage_before == pytest.approx(1.0)
    # the group grows by splicing; a second insert keeps the existing members
    more, _ = insert_vias(stitched, root2, [as_vias(result, s)[0]])
    assert more.count('(group "bac-stitch"') == 1
    assert more.count("\t(via\n") == 2 + len(result.placed)


def test_insert_is_byte_stable_and_remove_restores():
    s = Settings(pitch=6, fine_pitch_pads=4)
    text, root, b = board(s)
    vias = as_vias(plan(b, s), s)
    once, _ = insert_vias(text, root, vias)
    twice, _ = insert_vias(text, root, vias)
    assert once == twice
    restored, removed = remove_vias(once, parse(once))
    assert removed == len(vias)
    assert restored == text
    assert remove_vias(text, root) == (text, 0)


def test_edge_fence_puts_vias_along_the_edge():
    s = Settings(pitch=6, edge_fence=True, fine_pitch_pads=4)
    _, _, b = board(s)
    result = plan(b, s)
    fence = [p for p in result.placed if p.fence]
    assert fence and result.fence_pitch == 3
    for p in fence:
        # the fill starts 1 mm inside the edge, so the fence sits where the via fits into it
        d = min(p.x - 1, 29 - p.x, p.y - 1, 19 - p.y)
        assert d == pytest.approx(0.3 + 0.05, abs=s.step)


def test_pitch_from_frequency():
    # λ/20 at 1 GHz in εr 4.4: 300 mm / 2.098 / 20
    assert pitch_from_frequency(1e9, 4.4, 20) == pytest.approx(299.792458 / math.sqrt(4.4) / 20, rel=1e-6)
    s = Settings(pitch=None, max_frequency_hz=1e9)
    assert s.effective_pitch(4.0) == pytest.approx(299.792458 / 2 / 20)
    assert Settings(pitch=None, max_frequency_hz=1e9, epsilon_r=1.0).effective_pitch(4.0) == pytest.approx(
        299.792458 / 20
    )


def test_validate_rejects_bad_values():
    with pytest.raises(ConfigError):
        validate(Settings(via_drill=0.7))
    with pytest.raises(ConfigError):
        validate(Settings(pitch=None))
    with pytest.raises(ConfigError):
        validate(Settings(courtyards="never"))
    with pytest.raises(ConfigError):
        validate(Settings(min_layers=0))
    validate(Settings())
