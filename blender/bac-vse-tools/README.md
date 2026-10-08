# bac-vse-tools v1.0.0

Build a CubeSat – one Blender extension for the Video Sequencer with the three helpers the BAC video work keeps needing: a bulk importer that lays a folder of clips end to end, a proxy builder that takes one strip at a time, and a meta separator that keeps the trim. They appear as three panels in the VSE sidebar's VSE Tools tab (press N in the sequencer), and the meta separator also in the Strip menu.

The extension replaces the three 1.x add-ons `vse_bulk_import_addon.py`, `vse_build_proxies_addon.py` and `unmeta_trim_addon.py`; §5 lists what changed.

## 1. Install

Blender 4.2 LTS or newer. Build the zip from `src/bac_vse_tools/` (the manifest sits at its root, so a plain archive of that folder is what Blender expects):

```sh
cd blender/bac-vse-tools/src/bac_vse_tools
zip -r ../../bac_vse_tools-1.0.0.zip . -x '__pycache__/*'
# or, with Blender on the PATH, the validating way:
blender --command extension build --source-dir . --output-dir ../..
```

Then in Blender: Edit → Preferences → Get Extensions → the drop-down at the top right → Install from Disk, and choose the zip (dropping the zip into the Blender window works too). The tab appears in the sequencer's sidebar once a Video Sequencer editor is open. Updating is the same with a newer zip; Blender keeps the settings, which live in the `.blend` file (§4).

## 2. Bulk Import

Imports every video and audio file of a folder, in natural name order (`clip2` before `clip10`), one file per timer tick, each at the end of what is already on the timeline. Videos go through Blender's own Add Movie, so the layout is Blender's – the sound strip on channel 1 and the movie above it on channel 2 – and so is the sync: a clip whose frame rate differs from the scene's is retimed rather than stretched, and the audio keeps its stream offset. Audio-only files land on channel 1. Clips shorter than Minimum Length are left out, a file Blender cannot decode is retried and then skipped, and a clip without an audio track gets no sound strip. With Match Scene FPS on, the first readable video imported into an empty sequencer sets the scene's frame rate (29.97 becomes 30 over 1.001, as Blender stores it) and is added again at that rate; the summary names the change. Esc cancels, and the editor stays usable while the run goes on; the status box and Blender's status bar show the progress, and the result (imported, too short, failed) stays in the status box afterwards.

Autosave Copies is off by default. On, it writes a copy of the file into the Autosave Folder after every clip (`<file>_import_0007_of_0120.blend`) and asks for confirmation before the run starts. The open file itself is never saved by this tool – the 1.x add-on saved it after every clip, which made undo meaningless, and wrote the copies into the media folder.

Settings: Folder, Pause (s), Retries per File, Minimum Length (s), Match Scene FPS, Autosave Copies, Autosave Folder.

## 3. Sequential Proxies

Builds the proxies of the movie strips one after the other: select one, start Blender's build as a background job, watch the proxy file until it exists, has changed since the build was triggered and has stayed unchanged for Stable Time (s), then the next. Blender's own Rebuild Proxy queues every selected strip into one job with no per-strip progress and no way to stop between strips; this one shows which strip is building, reports each result, and stops on Esc. Blender exposes no status for the proxy job to Python, so the proxy file is the signal; Blender writes it under a temporary name and renames it when complete, so Stable Time is a margin, not a measurement. Timeout (s) bounds the wait for one strip whether the file has appeared or not; a timed-out strip is reported and the run moves on. With Skip Existing on (the default), a strip whose proxy file is already there is left alone – a second run over the same timeline builds only what is missing; off, every candidate is rebuilt. A strip that uses a custom proxy file is skipped (Blender builds nothing for it), two strips on the same file share one proxy and are built once, and movie strips inside meta strips are left out and counted, because Blender's build only reaches the open level of the timeline. The selection is put back when the run ends. The proxy file is looked for where Blender writes it – `BL_proxy/<file name>/proxy_25.avi` beside the source, the strip's own proxy directory, or the sequencer's project proxy directory (`//BL_proxy` beside the `.blend` when that setting is empty; for a file that was never saved that is a `BL_proxy` folder in Blender's working directory), whichever applies.

Settings: Strips (From Current Frame, Selected, All), Proxy Size (25 %, 50 %, 75 %, 100 %), Skip Existing, Stable Time (s), Check Interval (s), Timeout (s).

## 4. Strip Utilities

Separate Meta (Preserve Trim) ungroups the selected meta strips and clips their former children to the metas' in and out points. A child that lies entirely outside the meta's range would be removed; the operator says how many and asks first. The button is in the Strip Utilities panel and in the sequencer's Strip menu.

The settings of all three tools are one property group on the scene (`scene.bac_vse_tools`), saved with the `.blend` file. Labels are title case and carry units in parentheses, every property has a description for the tooltip, and each panel is laid out label → button → properties, as the BAC Project & Tooling Guide §5 asks (the guide calls them sub-panels; in Blender's terms they are the three panels of the VSE Tools category).

## 5. What changed against the 1.x add-ons

Must-fix items from the batch review: Bulk Import no longer saves the open file after every clip and no longer writes copies into the media folder (autosave is opt-in, into a folder of your choice, confirmed before the run); the proxy timeout now covers the whole wait and a proxy left over from an earlier build no longer counts as done; Separate Meta asks before it removes strips. Found while porting: the 1.x proxy builder called the synchronous path of Rebuild Proxy, so each encode blocked the interface and the file-watching that followed waited on a file that was already complete – the build is now a background job and the wait clock starts after it is triggered; its proxy path used the strip's name where Blender uses the file's, so a renamed strip's proxy was never found, and the project proxy directory was not resolved at all; its modal swallowed every click and key for the whole run. Also: settings in a property group instead of operator properties the panel reset on every redraw (the 1.x Bulk Import rows did nothing), the folder is a setting instead of a file browser, the Add Movie operator is called with explicit arguments and `set_view_transform` off (it otherwise switches the scene's colour management on the first import), the scene frame rate is written in the `fps / fps_base` form (Blender's `use_framerate` writes `3 / 0.1` for 30 fps), unreadable files are retried and then reported, the orphan sound datablocks of removed strips are cleaned up, Skip Existing and the custom and project proxy directories, movie strips inside metas and duplicate files handled, proxy size and scope as settings, the strips' selection restored after a proxy run, natural file order, the `strips` API with a fallback to `sequences` for 4.2 and 4.3, `cancel()` on both modal operators so a file load mid-run releases the timer, one extension with a manifest instead of three `bl_info` add-ons, MIT.

## 6. Tests

`tests/test_logic.py` covers the parts that need no Blender (file listing, frame maths, the proxy wait, the trim plan) on any Python; `tests/test_blender.py` runs inside Blender's Python when the `bpy` module is importable (`uv pip install bpy` in a Python 3.11 environment gives a headless Blender 4.5) and skips otherwise: registration, the 4.2 API fallback, the three tools' work on a sequencer made from ffmpeg-generated clips at 25 and 30 fps (the add operators run under a context override with a Video Sequencer area), proxies built as jobs into the three storage locations, and the zip installed and enabled by a second headless Blender. The modal timers, the confirm dialogs and the panels themselves need a window and are checked by hand in Blender.

```sh
uv run pytest blender                    # the logic tests; the Blender ones skip
.venv-bpy/bin/python -m pytest blender   # with bpy and ffmpeg: all of them
```

## 7. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 1.0.0 | 2026-10-07 | The three 1.x add-ons (`vse_bulk_import_addon.py` 1.3.0, `vse_build_proxies_addon.py` 1.2.0, `unmeta_trim_addon.py` 1.0.0) as one Blender extension with a manifest, three panels under VSE Tools, settings in a property group on the scene, and the changes in §5. 34 tests, 26 of them inside a headless Blender 4.5. |
