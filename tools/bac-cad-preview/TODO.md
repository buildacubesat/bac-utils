# bac-cad-preview – To-Do

Updated 2026-10-02 (v0.5.0). Completed items are kept in the "Done" section for one release, then removed.

## Verification

- [ ] **Lighting against `kicad-cli`.** Camera and framing are verified (see Done). KiCad's raytracer lights side faces darker and adds ambient occlusion; the Lambert constants in `raster.Lighting` were not tuned to it. Compare the ADCS placeholder renders side by side if the previews should look closer to the artifacts tool's.

## Correctness

- [ ] **Transparency in STEP is rendered opaque.** XCAF carries a transparency value per colour; the rasterizer has no alpha blending. Decide whether translucent housings matter for previews before adding a sorted second pass.
- [ ] **Unit of STL, OBJ and PLY is assumed to be millimetres.** A `--unit` flag (or a heuristic on the bounding box) would help with inch-based downloads.

## Performance

- [ ] **Memory peaks at about 1.2 GB for 1.3 million triangles** because the per-corner normals and the chunked span buffers are float32 arrays of the full mesh. Streaming the chunks straight from the face arrays would halve it.

## Roadmap

- [ ] **Fold into `bac-freecad-generate-artifacts`** as its preview stage once that tool exists. The render functions stay importable; the CLI here stays thin and may become an alias.

## Done (0.5.0)

- [x] `--face zp` compared against `kicad-cli pcb render` (2026-10-02): the ADCS placeholder board's STEP from `bac-kicad-generate-artifacts` 0.4.2 rendered with `--face zp` matches the tool's own `-render.webp` – silhouette IoU 0.996, identical 720 px bounding boxes and top-edge slopes. On the S-band antenna board the framing differs because kicad-cli frames the board outline while the preview frames the whole model (its ground-board part is larger than the PCB), and the board body is green in the STEP where KiCad shows the yellow mask – a property of the STEP export, not of the renderer.
- [x] Port onto `bac-common` (`make_parser`, `run`, `ui`); drop the mirrored `ui.py`.
- [x] Faces named with the project's axis letters (`xp` … `zm`); aliases kept.
- [x] Refuse two inputs that would write the same preview before any work.
