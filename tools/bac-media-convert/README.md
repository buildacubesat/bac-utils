# bac-media-convert v0.1.0

Build a CubeSat – the batch conversions the shop and the video work keep needing, as one tool with a subcommand per recipe. `webp-square` centre-crops product photos to squares and writes WebP; `cfr` re-encodes variable-frame-rate screen captures to constant-rate H.264 MP4 that editors handle. Both take files or folders, plan every output before starting, never overwrite silently, and show a progress bar with one ✓ line per file.

It replaces two shell loops (`convert_to_square_webp.sh` on ImageMagick, `webm-vfr-to-25fps.sh` on ffmpeg). ImageMagick is no longer needed; ffmpeg 5.1 or newer is, for `cfr` only.

## 1. Install

```sh
uv tool install ./tools/bac-media-convert     # from the bac-utils checkout
bac-media-convert webp-square photos/
```

No `--init`: every setting is a flag.

## 2. Usage

```
bac-media-convert webp-square PATH... [--out-dir DIR] [--max-side PX] [--quality Q] [--force] [--dry-run]
bac-media-convert cfr PATH... [--out-dir DIR] [--fps N] [--crf N] [--force] [--dry-run]
```

`PATH` is a file (taken as given, whatever its extension) or a folder, listed one level deep for the extensions the subcommand handles: `jpg`, `jpeg`, `png`, `tif`, `tiff` for `webp-square`; `webm`, `mkv`, `mov`, `mp4`, `m4v`, `avi` for `cfr`. Outputs land beside their inputs unless `--out-dir DIR` is given (created if missing). `--dry-run` lists what would be written.

Before anything is converted the run is planned: two inputs that would write the same file (`a.jpg` and `a.png` both become `a.webp`) stop the run with exit 2 and the pair named. An output that already exists is skipped with a `!` line and counted in the summary; `--force` converts it again. Re-running on a folder is therefore cheap: only new files are converted.

Each output is written as `<name>.part<ext>` and renamed into place when the conversion has finished, so an interrupted run (Ctrl-C, a crash) leaves no half-written file that the next run would skip as done. A file that cannot be read or encoded fails with a ✗ line and the run continues; the exit code is then 1. The summary (inputs, converted, skipped, failed) is printed on every path.

### 2.1 webp-square

Centre crop to `min(width, height)`, downscale so the longer side is at most `--max-side` (default 3840 px, never upscaled), export as WebP with `--quality` (default 90) and encoder method 6. The EXIF orientation of phone photos is applied before cropping, so what you see is what gets cropped; the ICC colour profile is kept, camera EXIF is not. Alpha is kept for PNGs that have it. Output name: `<stem>.webp`.

### 2.2 cfr

```
ffmpeg -hide_banner -loglevel error -n -i IN
       -vf crop=trunc(iw/2)*2:trunc(ih/2)*2 -r 25 -fps_mode cfr
       -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p OUT
```

`--fps` (default 25) and `--crf` (default 18, lower is better quality) are the two knobs. Audio streams are passed to ffmpeg's defaults. Output name: `<stem>_<fps>fps.mp4`, the name the shell loop produced. ffmpeg is called with an argument list, never through a shell, and `-n` makes ffmpeg itself refuse to overwrite as a second guard. A missing ffmpeg is reported by name before any work starts (as a warning under `--dry-run`). When a folder is listed, files already named `*_<N>fps.mp4` – this tool's own earlier outputs – are left alone; name one explicitly to re-encode it anyway.

Exit codes: `0` everything converted or skipped, `1` at least one file failed or ffmpeg is missing, `2` bad arguments or an output collision.

## 3. Reusing the WebP export

`bac_media_convert.webp` is importable: `load_oriented(path)`, `square_crop(image)`, `fit_max_side(image, px)`, `export_webp(image, target, quality=, method=)` returning the file size, and `convert_square_webp(source, target, max_side=, quality=)`. `bac-shop-product-cropper` will build its size-targeted export on `export_webp` when it is ported.

## 4. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-09-04 | Two shell loops merged into one Typer tool on `bac-common`: `webp-square` on Pillow (drops ImageMagick), `cfr` on ffmpeg via argv with `-fps_mode cfr` instead of the deprecated `-vsync`. Files or folders, `--out-dir`, output collisions refused before work, existing outputs skipped unless `--force` (the loops overwrote silently and `a.jpg`/`a.png` collided on `a.webp`), EXIF orientation applied, progress bar and per-file ✓/✗ lines, summary, `--dry-run`, `-v`, hidden `--debug`; `ffmpeg` absent reported by name; a folder listing leaves the tool's own `_<fps>fps.mp4` outputs alone; outputs written as `.part` files and renamed when complete. 26 tests, ffmpeg mocked. |
