# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from bac_common.cad import StepHeaderError, read_step_header, set_step_header, step_product_names

SAMPLE = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Open CASCADE Model'),'2;1');
FILE_NAME('/tmp/work/board.step','2026-10-02T07:02:11',(''),(''),
  'Open CASCADE STEP processor 7.8','Open CASCADE 7.8','Unknown');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1 = APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#2);
#7 = PRODUCT('board','board','',(#8));
#20 = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#7));
#31 = PRODUCT('Mänu''s part','Mänu''s part','',(#8));
ENDSEC;
END-ISO-10303-21;
"""


@pytest.fixture
def step(tmp_path: Path) -> Path:
    p = tmp_path / "board.step"
    p.write_text(SAMPLE, encoding="utf-8")
    return p


def test_read_header(step):
    h = read_step_header(step)
    assert h.name == "/tmp/work/board.step"
    assert h.time_stamp == "2026-10-02T07:02:11"
    assert h.author == [""] and h.organization == [""]
    assert h.preprocessor_version == "Open CASCADE STEP processor 7.8"
    assert h.authorization == "Unknown"


def test_set_header_fills_empty_fields_and_keeps_the_data(step):
    before = step.read_text(encoding="utf-8")
    h = set_step_header(step, name="bac-eps-board-v1r2-model.step", author="Mänu", organization="Build a CubeSat")
    assert h.author == ["Mänu"] and h.organization == ["Build a CubeSat"]
    after = step.read_text(encoding="utf-8")
    assert after.split("DATA;")[1] == before.split("DATA;")[1]
    # non-ASCII is written in Part 21's control-directive form, so any reader can take the header
    assert (
        "FILE_NAME('bac-eps-board-v1r2-model.step','2026-10-02T07:02:11',('M\\X2\\00E4\\X0\\nu'),('Build a CubeSat'),"
        in after
    )
    assert "FILE_SCHEMA" in after and "FILE_DESCRIPTION" in after
    assert read_step_header(step) == h


def test_set_header_respects_existing_values_unless_overwrite(step):
    set_step_header(step, author="A", organization="O", authorization="Unknown")
    h = set_step_header(step, author="B", organization="P")
    assert h.author == ["A"] and h.organization == ["O"]
    h = set_step_header(step, author="B", overwrite=True)
    assert h.author == ["B"] and h.organization == ["O"]
    assert h.authorization == "Unknown"  # a non-empty field is kept without overwrite


def test_quotes_and_non_ascii_round_trip(step):
    h = set_step_header(step, author="Mänu's lab 𝔸", organization="a);b", overwrite=True)
    text = step.read_text(encoding="utf-8")
    assert "('M\\X2\\00E4\\X0\\nu''s lab \\X4\\0001D538\\X0\\')" in text and "('a);b')" in text
    assert read_step_header(step) == h  # the entity end is found past the quoted ");"
    assert read_step_header(step).author == ["Mänu's lab 𝔸"]


def test_unchanged_header_is_not_rewritten(step):
    mtime = step.stat().st_mtime_ns
    data = step.read_bytes()
    set_step_header(step)
    assert step.read_bytes() == data and step.stat().st_mtime_ns == mtime


def test_not_a_step_file(tmp_path):
    p = tmp_path / "x.step"
    p.write_text("solid box\nendsolid box\n")
    with pytest.raises(StepHeaderError):
        read_step_header(p)
    p.write_text("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('x'),'2;1');\nENDSEC;\n")
    with pytest.raises(StepHeaderError, match="FILE_NAME"):
        read_step_header(p)


def test_product_names(step):
    assert step_product_names(step) == ["board", "Mänu's part"]
