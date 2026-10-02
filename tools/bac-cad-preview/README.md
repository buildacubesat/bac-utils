# bac-cad-preview v0.5.0

Build a CubeSat – renders STEP, STL and 3MF files to 720 × 720 px lossless WebP previews with a transparent background, framed exactly like the 3D render that `bac-kicad-generate-artifacts` makes from a KiCad board: same crop and padding, same output size, and the same camera when asked for the board view. A small X/Y/Z scale gizmo sits bottom left. The renderer is a numpy z-buffer rasterizer: no OpenGL, no display, no FreeCAD or KiCad installation needed.

The tool is the preview stage of the planned `bac-freecad-generate-artifacts`, the FreeCAD counterpart of the KiCad artifacts tool. Until that tool exists it runs on its own; its modules (`camera`, `mesh`, `raster`, `image`, `gizmo`) are plain imports so the preview becomes a stage there rather than a subprocess, and the CLI stays thin.

## 1. Install

```sh
uv tool install './tools/bac-cad-preview[step]'   # from the bac-utils checkout
bac-cad-preview part.step
```

The `step` extra pulls in `cadquery-ocp` (OpenCascade, about 100 MB) for STEP files. Without it the tool renders STL, 3MF, OBJ and PLY and tells you how to add STEP support when it meets a STEP file. The tool depends on `bac-common` from this repository, so it installs from the checkout, not from PyPI.

No `--init`, `--config` or `--env-file`: the tool has no persistent settings and no secrets.

## 2. Usage

```
bac-cad-preview [options] FILE [FILE ...]
```

```sh
bac-cad-preview bac-rail-3u-v2r1-chamfer-fdm.3mf
bac-cad-preview --face zp --out-dir ~/Desktop/previews bac-eps-*.step
bac-cad-preview --face xm --color '#A9ADB2' --gizmo-unit 10 bracket.stl
```

Each input becomes `<stem>.webp` next to it, or in `--out-dir DIR` (created if missing). Previews are regenerated on purpose, so an existing output is overwritten in place and the ✓ line says `(overwritten)`. Two inputs that would write the same file (`part.stl` and `part.step` both become `part.webp`) stop the run with exit 2 before any work; so does an `--out-dir` that exists and is not a directory. `--dry-run` lists the planned outputs and writes nothing. OFF, GLB and glTF files are accepted as well (trimesh reads them) but are not part of the project's workflow and untested. A file that cannot be read fails with a ✗ line and the run continues; an unsupported extension is skipped with a `!` line. The summary (files, rendered, failed, skipped) is printed on every path.

Exit codes: `0` every file rendered or skipped, `1` at least one file failed, `2` bad arguments or an output collision.

## 3. How the view is built

The view is "one model face toward the viewer, then the kicad-cli oblique". `--face` names the model axis that faces the viewer, in the project's axis letters: `xp`, `xm`, `yp`, `ym`, `zp`, `zm`. Z stays up on screen for the X and Y faces, and Y is up for `zp` and `zm` (the KiCad board frame). The signed spellings (`x`, `-x`, `+y` …) and kicad-cli's side names (`top` = `zp`, `front` = `ym`, `bottom` = `zm` …) are accepted as aliases; the log line always shows the letter form. On top of that base frame the oblique rotation Rx(x) · Ry(y) · Rz(z) is applied exactly as `kicad-cli pcb render --rotate` does it (glm::rotate chain in KiCad's `CAMERA::updateRotationMatrix`), default `22.5,-22.5,0`, orthographic projection, model centred on its bounding box.

- `--face auto` (default): `ym`, i.e. Z up with the camera front right at 22.5° azimuth and 22.5° elevation – the orientation FreeCAD parts are modelled in. For a flat part the thin axis faces the viewer instead, so an 81 × 81 × 6 mm end piece or a populated board shows its large face rather than its edge. A part counts as flat when both other extents are at least `--flat-ratio` (default 3) times the thinnest one; a rail with two small extents is not flat and stays Z up. The log line says which face was chosen.
- `--face zp`: the `bac-kicad-generate-artifacts` render view. A KiCad STEP export has its front copper toward Zp and the board top edge toward Yp, so a board STEP comes out in the same orientation as the artifacts render (and `auto` picks `zp` for most boards on its own).
- `--rotate X,Y,Z`: other oblique angles, same meaning as in kicad-cli.

Framing is the artifacts pipeline: render at 2160 × 2160 px, crop to the content, pad by 10 % of the content size per side, centre on a square canvas, resize to 720 px, save as lossless WebP (Pillow's libwebp at method 6, as `cwebp -z 9` did).

## 4. Colours and materials

STEP files carry colours per solid and per face (XCAF). KiCad's and FreeCAD's exporters write them, so a board renders with its mask, pads and the component models' own colours. A face without a colour inherits its solid's, then the assembly instance's, then `--color`. STEP has no material model beyond colour and transparency; transparency is ignored and everything renders opaque.

STL has no colour at all, and 3MF, OBJ and PLY usually none either, so mesh files render in RBF red (`#DA291C`): parts that exist as STL or 3MF are prints and jigs, not flight hardware, and the colour says so at a glance. STEP faces without a colour get a neutral grey (`#A9ADB2`) instead. `--color HEX` replaces both. Per-face or per-vertex colours in OBJ, PLY and 3MF files are used when present.

Shading is two-sided Lambert with an ambient floor, a camera headlight, a key light from the upper left and a light along the model's Zp axis, which stands in for KiCad's side lights at elevation 90. Thin dark lines mark silhouettes and creases so flat-shaded geometry stays readable (`--no-edges` turns them off). KiCad's raytraced shadows and ambient occlusion are not reproduced.

## 5. Scale gizmo

The gizmo bottom left draws the model's Xp (red), Yp (green) and Zp (blue) axes, rotated with the view and projected at the image's own px/mm, so it is a true scale and orientation reference and an axis along the viewing direction is foreshortened like the model. Each axis runs from an origin dot to an end bar one main unit away. The unit text is written along the most horizontal axis, underneath it and rotated with it, so the dot-to-bar distance reads as a dimension. The unit is chosen from the 1-2-5 series (1, 2, 5, 10, 20, 50 mm …) as the largest whose axis stays within 90 px, or set with `--gizmo-unit`; since the arms are true scale, their length only changes when the unit steps. Where the gizmo overlaps the model a faint light halo keeps it legible. `--no-gizmo` omits it.

The gizmo text uses Nunito or IBM Plex Sans when one of them is installed, otherwise DejaVu Sans, Liberation Sans or Arial, otherwise Pillow's built-in font.

## 6. Examples

`examples/` holds three small models to try the tool on: `bracket.stl` (an L bracket with a boss, 40 × 25 × 20 mm, not flat), `demo-board.step` (a 22 × 17.5 mm board with coloured parts) and `assembly-board.step` (a 100 × 80 mm board with 34 instanced parts). `examples/make_examples.py` regenerates them; it needs the `step` extra.

## 7. Limitations

- STL, OBJ and PLY carry no unit; the tool assumes millimetres. 3MF declares its unit and is converted to millimetres.
- Tessellation tolerance for STEP is derived from the model size (`--deflection` overrides it). Very large assemblies take a while; a part used many times in an assembly is tessellated once.
- Memory grows with triangle count: about 1.2 GB peak for 1.3 million triangles.
- The `--face zp` view is derived from KiCad's camera source, not yet compared pixel for pixel against a `kicad-cli` render of the same board (see `TODO.md`).

## 8. Development

From the bac-utils root:

```sh
uv run pytest tools/bac-cad-preview
uv run ruff check tools/bac-cad-preview && uv run ruff format --check tools/bac-cad-preview
```

The STEP loader test runs only when `cadquery-ocp` is importable (`uv pip install cadquery-ocp` into the workspace environment) and is skipped otherwise. Rendering tests draw synthetic quads and boxes and need no model files.

## 9. License

MIT – see the BAC licensing conventions (software: MIT, hardware: CERN OHL-S 2.0, documentation: CC BY-SA 4.0).

## 10. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.5.0 | 2026-10-02 | Joins bac-utils on `bac-common` (`make_parser`, `run`, `ui`; the mirrored `ui.py` is gone). Faces are named with the project's axis letters `xp`, `xm`, `yp`, `ym`, `zp`, `zm`; the signed spellings and kicad-cli side names stay as aliases and the log prints the letter form. `-o/--out` becomes `--out-dir DIR` as in the other batch tools. Two inputs that would write the same preview are refused before any work, and so is an `--out-dir` that is not a directory. One bad file no longer ends the batch: every failure inside the render of a file prints its ✗ line and the run continues (0.4.1 caught only load and I/O errors). `samples/` becomes `examples/`; the font lookup for the gizmo runs once per size. Tests on `bac_common.testing`; 43 tests. |
| 0.4.1 | 2026-10-01 | Gizmo letters sit a little further from the end bars. |
| 0.4.0 | 2026-10-01 | Mesh files (STL, 3MF, OBJ, PLY) render in RBF red by default; STEP keeps the neutral grey for uncoloured faces; `--color` overrides both. |
| 0.3.1 | 2026-10-01 | Gizmo: half-unit tick removed. |
| 0.3.0 | 2026-10-01 | `--view`/`--side` replaced by `--face AXIS` (auto, x, y, z, -x, -y, -z, kicad-cli side names as aliases); `auto` keeps Z up and turns the thin axis of a flat part toward the viewer, threshold `--flat-ratio`. Gizmo letters are Xp/Yp/Zp; the unit text follows the most horizontal axis. |
| 0.2.0 | 2026-10-01 | Default view is now `part` (Z up, FreeCAD orientation); the KiCad render view is `--view board`, `--side`/`--rotate` override either. Gizmo moved bottom left and redrawn as origin dot, end bar, half tick and the unit text under the X span. 3MF support (networkx, lxml). Roadmap note on `bac-freecad-generate-artifacts`. |
| 0.1.0 | 2026-10-01 | Initial release: STEP (with XCAF colours, assemblies and instancing) and STL/OBJ/PLY/3MF input, numpy z-buffer renderer with kicad-cli camera conventions, artifacts-tool framing, scale gizmo, edge lines, house CLI with `--dry-run`, `--side`, `--rotate`, `--color`, `--gizmo-unit`, `--no-gizmo`, `--no-edges`, `--deflection`. |
