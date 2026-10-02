# SPDX-License-Identifier: MIT
"""bac-cad-preview – STEP, STL and 3MF files to square WebP previews.

A batch tool: every input becomes ``<stem>.webp`` beside it or in ``--out-dir``.
Previews are regenerated on purpose, so an existing output is overwritten in
place and the ✓ line says so; two inputs that would write the same file stop
the run before any work. No persistent settings and no secrets, so no
``--init``, ``--config`` or ``--env-file``.

Exit codes: 0 every file rendered or skipped, 1 at least one file failed,
2 bad arguments or an output collision.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.errors import UsageError

from . import TOOL_NAME, __version__
from .camera import DEFAULT_FACE, DEFAULT_ROTATE, FLAT_RATIO, auto_face, normalize_face, parse_rotate, view_rotation
from .gizmo import GizmoSpec, choose_unit, draw_gizmo
from .image import OUTPUT_SIZE, crop_pad_square_resize_rgba, write_webp
from .mesh import STEP_INSTALL_HINT, SUPPORTED_SUFFIXES, LoadError, hex_to_rgb, kind_of, load, step_available
from .raster import render

STEP_COLOR = "#A9ADB2"  # neutral grey for STEP faces without a colour
MESH_COLOR = "#DA291C"  # RBF red for STL/3MF/OBJ/PLY: these parts are not for flight
DESCRIPTION = "Render STEP, STL and 3MF files to WebP previews framed like the KiCad renders."


@dataclass
class Options:
    files: list[Path]
    out_dir: Path | None
    rotate: tuple[float, float, float]
    face: str
    flat_ratio: float
    color: tuple[float, float, float] | None
    gizmo_unit: float | None
    gizmo: bool
    edges: bool
    deflection: float | None
    dry_run: bool


def main() -> None:
    bac_cli.run(_main)


def build_parser():
    p = bac_cli.make_parser(
        TOOL_NAME,
        __version__,
        DESCRIPTION,
        examples=[
            f"{TOOL_NAME} bac-rail-3u-v2r1.3mf",
            f"{TOOL_NAME} --face zp --out-dir ~/Desktop/previews bac-eps-*.step",
        ],
        init=False,
        env_file=False,
        config=False,
    )
    p.usage = f"{TOOL_NAME} [options] FILE [FILE ...]"
    rot_default = ",".join(f"{a:g}" for a in DEFAULT_ROTATE)
    p.add_argument("files", nargs="+", metavar="FILE", help="STEP/STP, STL, OBJ, PLY, 3MF files")
    p.add_argument("--out-dir", metavar="DIR", help="output directory (default: next to each input)")
    p.add_argument(
        "--face", metavar="AXIS", default=DEFAULT_FACE, help="axis toward the viewer: auto, xp, xm, yp, ym, zp, zm"
    )
    p.add_argument(
        "--flat-ratio",
        metavar="N",
        type=float,
        default=FLAT_RATIO,
        help=f"flat part: others N × the thin extent (default {FLAT_RATIO:g})",
    )
    p.add_argument(
        "--rotate", metavar="X,Y,Z", default=rot_default, help=f"kicad-cli --rotate angles (default {rot_default})"
    )
    p.add_argument("--color", metavar="HEX", help="colour for faces without one (RBF red; grey for STEP)")
    p.add_argument("--gizmo-unit", metavar="MM", type=float, help="gizmo main unit in mm (default: auto, 1-2-5 series)")
    p.add_argument("--no-gizmo", action="store_true", help="omit the scale gizmo")
    p.add_argument("--no-edges", action="store_true", help="omit the thin edge lines")
    p.add_argument("--deflection", metavar="MM", type=float, help="STEP tessellation tolerance in mm (default: auto)")
    return p


def parse_options(argv: list[str]) -> Options:
    args = build_parser().parse_args(argv)
    try:
        face = normalize_face(args.face)
        rotate = parse_rotate(args.rotate)
        color = hex_to_rgb(args.color) if args.color else None
    except ValueError as e:
        raise UsageError(str(e)) from e
    if args.flat_ratio < 1:
        raise UsageError("--flat-ratio must be at least 1.")
    if args.gizmo_unit is not None and args.gizmo_unit <= 0:
        raise UsageError("--gizmo-unit must be positive.")
    if args.deflection is not None and args.deflection <= 0:
        raise UsageError("--deflection must be positive.")
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if out_dir is not None and out_dir.exists() and not out_dir.is_dir():
        raise UsageError(f"--out-dir {args.out_dir} is not a directory.")
    return Options(
        files=[Path(f).expanduser() for f in args.files],
        out_dir=out_dir,
        rotate=rotate,
        face=face,
        flat_ratio=args.flat_ratio,
        color=color,
        gizmo_unit=args.gizmo_unit,
        gizmo=not args.no_gizmo,
        edges=not args.no_edges,
        deflection=args.deflection,
        dry_run=args.dry_run,
    )


def output_path(src: Path, out_dir: Path | None) -> Path:
    return (out_dir if out_dir else src.parent) / f"{src.stem}.webp"


def check_collisions(files: list[Path], out_dir: Path | None) -> None:
    """Two supported inputs that would write the same preview are an error before any work starts.

    The same file named twice is not a collision; unsupported files are skipped later and do not count."""
    seen: dict[Path, Path] = {}
    for src in files:
        if kind_of(src) == "unknown":
            continue
        dst = output_path(src, out_dir).resolve()
        if dst in seen and seen[dst].resolve() != src.resolve():
            raise UsageError(
                f"{seen[dst]} and {src} would both write {dst.name}.",
                "Rename one input or render them into different --out-dir folders.",
            )
        seen.setdefault(dst, src)


def fmt_int(n: int) -> str:
    """Thousands separator per the guide: 12'345."""
    return f"{n:,}".replace(",", "'")


def render_file(src: Path, dst: Path, opt: Options) -> dict:
    """Load, render, frame, decorate and write one file; returns stats for the log line."""
    t0 = time.perf_counter()
    with ui.spinner(f"Loading {ui.esc(src.name)}"):
        fallback = opt.color or hex_to_rgb(STEP_COLOR if kind_of(src) == "step" else MESH_COLOR)
        mesh = load(src, fallback, opt.deflection)
    size = mesh.size_mm()
    extra = ""
    if mesh.stats.get("format") == "step":
        extra = f", {mesh.stats['parts']} parts, deflection {mesh.stats['deflection_mm']:.3g} mm"
    if mesh.stats.get("colored"):
        colored = "model colours"
    elif opt.color:
        colored = "--color"
    else:
        colored = "default grey" if kind_of(src) == "step" else "RBF red"
    ui.ok(
        f"Loaded {ui.path(src.name)}: {fmt_int(mesh.n_triangles)} triangles, "
        f"{size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f} mm, {colored}{extra}"
    )

    face, auto = opt.face, False
    if face == "auto":
        face, flat = auto_face(size, opt.flat_ratio)
        auto = True
        if flat:
            ui.dim(f"flat part: {face} faces the viewer")
    rot = view_rotation(opt.rotate, face)
    with ui.make_progress("percent") as progress:
        task = progress.add_task("Rendering", total=100)

        def advance(fraction: float) -> None:
            progress.update(task, completed=round(fraction * 100))

        result = render(mesh, rot, edges=opt.edges, progress=advance)
    framed = crop_pad_square_resize_rgba(Image.fromarray(result.image, "RGBA"))
    px_per_mm = result.px_per_mm * framed.scale
    img = framed.image
    unit = None
    if opt.gizmo:
        unit = opt.gizmo_unit if opt.gizmo_unit else choose_unit(px_per_mm)
        img = draw_gizmo(img, GizmoSpec(unit_mm=unit, px_per_mm=px_per_mm, rot=rot, size=OUTPUT_SIZE))
    existed = dst.exists()
    nbytes = write_webp(img, dst)
    return {
        "bytes": nbytes,
        "seconds": time.perf_counter() - t0,
        "unit": unit,
        "face": face + (" auto" if auto else ""),
        "px_per_mm": px_per_mm,
        "overwritten": existed,
    }


def _main(argv: list[str], debug: bool) -> int:
    opt = parse_options(argv)
    check_collisions(opt.files, opt.out_dir)
    ui.opening(TOOL_NAME, __version__, DESCRIPTION)
    rendered = failed = skipped = 0
    step_ok = step_available()
    rotate_text = ",".join(f"{a:g}" for a in opt.rotate)

    for src in opt.files:
        dst = output_path(src, opt.out_dir)
        if not src.is_file():
            ui.fail(f"{ui.path(src)}: not found")
            failed += 1
            continue
        kind = kind_of(src)
        if kind == "unknown":
            supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
            ui.warn(f"{ui.path(src.name)}: unsupported type {ui.esc(repr(src.suffix))}, skipped (supports {supported})")
            skipped += 1
            continue
        if kind == "step" and not step_ok:
            ui.fail(f"{ui.path(src.name)}: STEP support missing – {ui.esc(STEP_INSTALL_HINT)}")
            failed += 1
            continue
        if opt.dry_run:
            ui.step(f"{ui.path(src.name)} → {ui.path(dst)} ({kind}, face {opt.face}, rotate {rotate_text})")
            rendered += 1
            continue
        try:
            stats = render_file(src, dst, opt)
        except LoadError as e:
            ui.fail(f"{ui.path(src.name)}: {ui.esc(e.message)}")
            failed += 1
            continue
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 – one bad file (OCP failure, numpy error) must not end the batch
            reason = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            ui.fail(f"{ui.path(src.name)}: {ui.esc(reason)}")
            if debug:
                ui.err_console.print(traceback.format_exc(), highlight=False, markup=False)
            failed += 1
            continue
        gizmo = f", gizmo {stats['unit']:g} mm" if stats["unit"] else ""
        over = " [dim](overwritten)[/dim]" if stats["overwritten"] else ""
        ui.ok(
            f"Wrote {ui.path(dst)} ({stats['bytes'] / 1024:.0f} KB, face {stats['face']}, "
            f"{stats['px_per_mm']:.1f} px/mm{gizmo}, {stats['seconds']:.1f} s){over}"
        )
        rendered += 1

    ui.summary(
        [
            ("Files", len(opt.files)),
            ("Planned" if opt.dry_run else "Rendered", rendered),
            ("Failed", failed),
            ("Skipped", skipped),
        ],
        dry_run=opt.dry_run,
    )
    return 1 if failed else 0
