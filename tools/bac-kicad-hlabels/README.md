# bac-kicad-hlabels v0.1.0

Build a CubeSat – emits `(hierarchical_label …)` blocks for a list of net names, staggered on a 2.54 mm pitch so they land without overlapping. Paste the output into a `.kicad_sch` (between two existing items) or keep it as a snippet. The blocks are complete: shape, position, font effects, justification and a fresh UUID each, in the form KiCad 9 and 10 write themselves.

## 1. Install

```sh
uv tool install ./tools/bac-kicad-hlabels     # from the bac-utils checkout
bac-kicad-hlabels examples/nets.txt | head
```

No `--init`: every setting is a flag.

## 2. Usage

```
bac-kicad-hlabels [INPUT] [-o FILE] [--at X Y] [--step MM] [--rotation DEG]
                  [--font-size MM] [--shape S] [--justify J] [--gap-on-blank]
```

`INPUT` holds one net name per line; without it (or with `-`) the tool reads stdin. Output goes to stdout unless `-o FILE` is given.

| Flag | Default | Meaning |
| :-- | :-- | :-- |
| `--at X Y` | `0 0` | position of the first label, in mm |
| `--step MM` | `2.54` | Y distance from one label to the next |
| `--rotation DEG` | `0` | `0`, `90`, `180` or `270` |
| `--font-size MM` | `1.27` | font width and height |
| `--shape S` | `passive` | `input`, `output`, `bidirectional`, `tri_state` or `passive` |
| `--justify J` | `right` | `left` or `right` |
| `--gap-on-blank` | off | a blank input line leaves one slot empty instead of being ignored |

`--gap-on-blank` is for inputs that mirror a connector or a sheet pin column: `examples/nets.txt` groups its 38 nets with blank lines, and with the flag the groups keep their spacing in the schematic (four blank lines leave four empty slots). Trailing blank lines never add slots.

Positions are computed as `Y + n × step`, not accumulated, so the fortieth label sits at exactly `99.06`, and numbers are written with up to four decimals like KiCad does. Names containing `"` or `\` are escaped.

Exit codes: `0` written, `1` no names in the input or the output could not be written, `2` bad arguments.

## 3. Output

```
(hierarchical_label "A_CAN_1_P"
	(shape passive)
	(at 0 0 0)
	(effects
		(font
			(size 1.27 1.27)
		)
		(justify right)
	)
	(uuid "0b6e2b3c-…")
)
```

## 4. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-09-04 | Packaged on `bac-common` from the `gen-hlabels.py` script. Geometry, font, shape and justification as flags with the script's values as defaults; `-o FILE`; `--gap-on-blank` for grouped inputs; positions multiplied instead of accumulated; UUID quoted as KiCad 9 writes it; name escaping; `-v` and hidden `--debug`; exit 2 for usage errors. KiCad 9/10 baseline stated (the script's docstring said v6). 23 tests. |
