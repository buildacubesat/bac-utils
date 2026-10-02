# bac-cad-preview – To-Do

Updated 2026-10-02 (v0.5.0). Completed items are kept in the "Done" section for one release, then removed.

## Verification

- [ ] **Compare `--face zp` against a real `kicad-cli pcb render`.** The view is derived from KiCad's `camera.cpp` and the render job handler, not checked pixel for pixel. Render the deployment-switch STEP that `bac-kicad-generate-artifacts` exports (its step-6 fixture) and set it beside the WebP the artifacts tool makes from the same board; adjust the lighting constants in `raster.Lighting` if the two disagree.

## Correctness

- [ ] **Transparency in STEP is rendered opaque.** XCAF carries a transparency value per colour; the rasterizer has no alpha blending. Decide whether translucent housings matter for previews before adding a sorted second pass.
- [ ] **Unit of STL, OBJ and PLY is assumed to be millimetres.** A `--unit` flag (or a heuristic on the bounding box) would help with inch-based downloads.

## Performance

- [ ] **Memory peaks at about 1.2 GB for 1.3 million triangles** because the per-corner normals and the chunked span buffers are float32 arrays of the full mesh. Streaming the chunks straight from the face arrays would halve it.

## Roadmap

- [ ] **Fold into `bac-freecad-generate-artifacts`** as its preview stage once that tool exists. The render functions stay importable; the CLI here stays thin and may become an alias.

## Done (0.5.0)

- [x] Port onto `bac-common` (`make_parser`, `run`, `ui`); drop the mirrored `ui.py`.
- [x] Faces named with the project's axis letters (`xp` … `zm`); aliases kept.
- [x] Refuse two inputs that would write the same preview before any work.
