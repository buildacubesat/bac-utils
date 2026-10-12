# SPDX-License-Identifier: MIT
"""Fixture texts shared by the maintain tests: a small board and a small schematic."""

from __future__ import annotations

from bac_kicad_maintain.config import DEFAULTS, Settings
from bac_kicad_maintain.maintain import Outcome, transform

from bac_common.sexp import parse

BOARD = r"""(kicad_pcb (version 20260101) (generator pcbnew)
  (net 0 "") (net 1 "GND") (net 2 "SIGNAL")
  (gr_text "a (label) \"quoted\"" (at 10 20 135) (layer "B.SilkS")
    (uuid "board-text")
    (effects (font (size 1 2) (thickness 0.2) bold italic)
      (justify left bottom mirror) hide))
  (gr_text_box "box" (start 1 1) (end 8 9) (angle 90) (layer "F.SilkS")
    (effects (font (size 1 1) (thickness 0.2)))
    (stroke (width 0.15) (type solid)))
  (footprint "A:B" (layer "F.Cu") (at 40 50 90) (uuid "fp")
    (property "Reference" "U1" (at 0 0 90) (unlocked yes) (layer "F.SilkS")
      (effects (font (size 1 1) (thickness 0.15)) (justify right top)))
    (property "Value" "IC" (at 0 1 90) (layer "F.Fab")
      (effects (font (size 1 1) (thickness 0.15)) hide))
    (property "metadata" "leave me unchanged")
    (fp_text user "custom" (at 0 2 90) unlocked (layer "F.SilkS")
      (effects (font (face "Font") (size 1 1) (thickness 0.15))))
    (fp_text_box "textbox" (start 0 0) (end 5 5) (layer "F.Fab")
      (effects (font (size 1 1) (thickness 0.15))))
    (fp_line (start 0 0) (end 1 1) (layer "F.CrtYd") (width 0.15))
    (fp_rect (start 0 0) (end 1 1) (stroke (width 0.12) (type solid))
      (fill none) (layer "B.CrtYd"))
    (fp_line (start 0 0) (end 1 1) (layer "F.SilkS") (width 0.15))
    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 2 "SIGNAL")))
  (dimension (type aligned) (layer "Dwgs.User")
    (gr_text "dimension" (at 0 0 0) (layer "Dwgs.User")
      (effects (font (size 5 5) (thickness 0.5)) (justify left))))
  (group "group" (uuid "group-id") (members "board-text"))
  (via (at 1 1) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1))
  (via (at 2 2) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 2))
  (via (at 3 3) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 0))
  (segment (start 1 1) (end 2 2) (width 0.3) (layer "F.Cu") (net 2)))
"""

SCHEMATIC = """(kicad_sch
  (lib_symbols
    (symbol "bac Library v1:C" (property "Value" "bac Library v1:C")
      (symbol "C_0_1" (text "don't change" (at 0 0 0))))
    (symbol "other:Q" (property "Value" "Q")))
  (symbol (lib_id "bac Library v1:C") (at 0 0 0)
    (property "Value" "bac Library v1:C"))
  (symbol (lib_id "bac Library v10:C") (at 1 1 0))
  (text "bac Library v1:C" (at 0 0 0)))
"""

LABELS = """(kicad_sch
  (label "local" (at 1 2 90) (effects
    (font (face "Font") (size 0.9 1.1) (thickness 0.08) bold italic)
    (justify left bottom) hide))
  (global_label "global" (shape input) (at 2 3 180)
    (effects (font (size 1 1)) (justify right))
    (property "Intersheetrefs" "${INTERSHEET_REFS}"
      (effects (font (size 2 2)))))
  (hierarchical_label "hier" (shape output) (at 3 4 0)
    (effects (font (size 0.7 0.7))))
  (text "notes" (at 0 0 0) (effects (font (size 3 3))))
  (text_box "box" (effects (font (size 4 4))))
  (symbol (lib_id "lib:C")
    (property "Reference" "C1" (effects (font (size 0.6 0.6))))
    (property "Value" "value" (effects (font (size 0.8 0.8)))))
  (sheet (pin "sheet pin" input (at 0 0 0)
    (effects (font (size 0.4 0.4)))))
  (lib_symbols (symbol "cached" (pin input line
    (name "PIN" (effects (font (size 0.5 0.5)))))))
  (directive_label (effects (font (size 0.3 0.3)))))"""


def run(
    text: str = BOARD,
    selected: set[str] | None = None,
    settings: Settings = DEFAULTS,
    command: str = "apply",
    **kwargs: str,
) -> Outcome:
    """``transform`` on a text, with the default selection the original script had."""
    selected = {"text", "courtyards"} if selected is None else selected
    return transform(text, parse(text), settings, command, selected, **kwargs)
