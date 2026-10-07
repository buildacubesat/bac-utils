# bac-store-product-cropper v0.2.0

Build a CubeSat – a small Tk window for framing product photos by hand, one after the other, and exporting each crop as a WebP file that stays under a size target. Made for the store's product images: `bac-media-convert webp-square` does the mechanical centre crop; this tool is for the photos where the centre is not the subject.

The tool may later be folded into a wider store artifact-generation tool (product images, listings and the like for the store). That tool is not designed yet; the crop and export functions here are importable so it can reuse them (§5).

## 1. Install

```sh
uv tool install ./tools/bac-store-product-cropper     # from the bac-utils checkout
bac-store-product-cropper photos/
```

Needs a Python with Tk (`python3-tk` on Debian and Ubuntu; the python.org and uv-managed builds include it). Without it the tool says so and exits 1.

## 2. Usage

```
bac-store-product-cropper [options] PATH...
```

`PATH` is an image file or a folder, listed one level for `.jpg`, `.jpeg`, `.png`, `.tif` and `.tiff` in any case. Each image gets one `<stem>.webp` in `out_webp/` beside it, or in `--out-dir DIR`. Outputs are planned before the window opens: two inputs that would write the same file are an error (exit 2, nothing written), and an output that exists is skipped with a `!` line unless `--force`. `--dry-run` prints the plan and stops.

In the window: scroll to zoom (5 % per notch, about the cursor), drag to pan, `R` resets to the largest centred crop, `Enter` or `Space` saves and moves on, `S` or `→` skips, `Q` or `Esc` quits. The crop keeps the ratio given with `--aspect RATIO` (`1` square, `0.5` for 1:2, `4/3` or `1.3333`, `2` for 2:1) and cannot shrink below 256 px wide. The preview has the same ratio as the crop, so what you see is what is exported. While a file is being written (a "Saving …" note shows; five encodes of a large crop take a few seconds) or the next image loads, keys are ignored.

Export: the crop is downscaled so its width is at most `--max-width PX` (3840; never upscaled), then encoded as WebP at `--start-q` (30) and, while the file is larger than `--target-kb KB` (200), again five quality points lower down to `--min-q` (10); the first encode under the target is kept, else the one at the floor. `--target-kb 0` encodes once at the start quality. The EXIF orientation is applied, the ICC profile travels with the pixels, transparency is kept.

The terminal prints one `✓` line per saved file with its pixel size, kilobytes and quality, `✗` for an image that could not be read or written, and a summary with Saved, Skipped (by hand or because the output existed), Failed and Remaining when the window was closed early. Exit codes: `0` finished or quit early, `1` at least one image failed or Tk is missing, `2` bad arguments.

## 3. Options

| Option | Default | Meaning |
| :-- | :-- | :-- |
| `--out-dir DIR` | `out_webp/` beside each source | where the WebP files go |
| `--aspect RATIO` | `1` | crop ratio, width over height; a decimal or a fraction such as `4/3` |
| `--max-width PX` | `3840` | longest output width; smaller crops are not enlarged |
| `--target-kb KB` | `200` | file size to get under; `0` encodes once |
| `--start-q Q` | `30` | first WebP quality tried |
| `--min-q Q` | `10` | lowest quality tried; must not exceed `--start-q` |
| `--force` | off | redo outputs that already exist |
| `--dry-run` | off | print the plan, open no window |

## 4. What changed against 0.1.0

Four bugs: pressing Enter a second time during the 800 ms pause saved the current crop under the next file's name (the window is now busy until the next image is on screen); the preview was drawn into a square and stretched every crop that was not 1:1 (the canvas now has the crop's ratio); `--start-q` below `--min-q` crashed with a `TypeError` (now a usage error); on a case-insensitive file system every file was listed twice (the listing de-duplicates by resolved path). Also: packaging with an entry point (0.1.0 had no build system and the name `product-cropper`), `-v`, errors to stderr, the opening panel and the summary, `--out-dir`, the collision check, `--force` and the skip of existing outputs, the WebP writer shared with `bac-media-convert`, more input formats, the `--method` option dropped (always 6, the slowest and smallest).

## 5. Adapting for your own project

Nothing here is specific to Build a CubeSat but the defaults. For reuse: `bac_store_product_cropper.crop.CropState` is the crop rectangle (`initial()`, `pan()`, `zoom()`, `reset()`, `box()`), `preview_size()` fits a ratio into a square canvas; `bac_store_product_cropper.export.ExportOptions` holds the numbers, `prepare(image, box, max_width)` crops and downscales, `export_sized(image, target, options)` steps the quality until the file is under the target, `save_crop()` does all three and returns size, quality and pixel dimensions. The GUI is `bac_store_product_cropper.gui.run(jobs, options, report=)` over `bac_media_convert.batch.Job` objects and imports Tk only when called.

## 6. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.2.0 | 2026-10-07 | Repackaged as `bac-store-product-cropper` on `bac-common` and `bac-media-convert`: the four bugs in §4 fixed, an unwritable output folder reported as a failed file instead of a dead window, `-v`, `--dry-run`, hidden `--debug`, `--out-dir`, `--force`, files and folders as inputs, collision check and skip of existing outputs, Rich opening panel, ✓/✗ lines and summary, errors to stderr, the preview canvas with the crop's ratio, the export on `bac_media_convert.webp.export_webp`, `--method` dropped; the crop and export logic in importable modules with 37 tests (the window's key handling against a fake `tkinter`). |
| 0.1.0 | – | `product_cropper.py`: the Tk cropper with size-targeted WebP export, no packaging. |
