# SPDX-License-Identifier: MIT
"""The stages, in the order they run, and what each one writes.

Every stage is a function of a :class:`Context` that returns a short note
for its ✓ line (``"21 KB"``, ``"11 files"``). Stages talk to kicad-cli
through ``ctx.run`` (a :class:`~.runner.Runner`), so a dry run records the
commands and writes nothing. Image work happens in Pillow: the render and
the pinout are saved as lossless WebP without an external encoder.

Targets kicad-cli 10.x (:data:`~.runner.TARGET_KICAD`). Zone fills are
exported as saved – ``--check-zones`` is never passed, so a panel's fills
stay as the panelizer left them and a board's fills are the ones its
designer last saw.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from bac_common.cad import set_step_header
from bac_common.catalog import Catalog, resolve
from bac_common.errors import ConfigError, ExternalToolError

from . import TOOL_NAME, __version__, bom
from .config import LEGACY_FIELDS, Settings
from .freeze import COPY_IGNORE, freeze_project, target_dir
from .project import Plan, normalize_export_names, rewrite_gbrjob
from .qr import insert_qr_file, substitute_variables
from .runner import Runner, Tools

__all__ = ["Context", "Stage", "STAGES", "STAGE_NAMES", "select_stages", "kb"]

# Render: a square PNG from the 3D viewer, cropped to the board, padded and resized to a 720 px square.
RENDER_PNG_SIZE = 2160
RENDER_ROTATE = "22.5,-22.5,0"
RENDER_ZOOM = "0.8"
RENDER_PRESET = "legacy_manual"
RENDER_WEBP_SIZE = 720
RENDER_PAD_FRAC = 0.10
WEBP_METHOD = 6  # Pillow's slowest, smallest lossless encoding, as cwebp -z 9 gave; tests turn it down

# Pinout: Edge.Cuts, F.Fab and F.Silkscreen as a 1920 × 1080 transparent plot, board 80 % of the height.
PINOUT_CANVAS = (1920, 1080)
PINOUT_HEIGHT_FRAC = 0.80
PINOUT_OVERSAMPLE = 4
PINOUT_LAYERS = "Edge.Cuts,F.Fab,F.Silkscreen"
PINOUT_SVG_ARGS = (
    "--black-and-white",
    "--page-size-mode",
    "2",
    "--exclude-drawing-sheet",
    "--crossout-DNP-footprints-on-fab-layers",
)

QR_MODULE_MIN_MM = 0.2  # a QR module smaller than this is below most fabs' silkscreen minimum feature

GERBER_LAYERS = ("F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask", "Edge.Cuts")
PANEL_LAYERS = ("User.Comments",)  # V-cut lines live here


@dataclass
class Context:
    run: Runner
    tools: Tools
    settings: Settings
    plan: Plan
    ibom: bool = False
    qr_text: str = ""
    open: bool = False  # --open: the iBOM may open its browser tab, the ZIP goes to GerbView
    debug: bool = False
    catalog: Catalog | None = None  # the part catalogs, when [catalog] names them: the bom stage resolves against them
    scheme: str = "thin"  # the BOM scheme of this run: thin (catalog resolution) or legacy (the symbols' own fields)
    freeze: str = ""  # --freeze: the build to write a frozen project for, or ""
    spinner: Callable[[str], object] = field(default=lambda message: _NoSpinner())
    board: Path | None = None  # the board the stages export: the project's, or the QR stage's copy
    failed: set[str] = field(default_factory=set)  # names of the stages that failed so far in this project
    shown: str | None = None  # a stage may name its output when it differs from the plan's placeholder

    def __post_init__(self) -> None:
        if self.board is None:
            self.board = self.plan.project.pcb_file


class _NoSpinner:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


def kb(path: Path) -> str:
    """A file size for the ✓ line: ``812 B``, ``3.4 KB``, ``118 KB``."""
    n = path.stat().st_size
    if n < 1024:
        return f"{n} B"
    return f"{n / 1024:.1f} KB" if n < 10240 else f"{n / 1024:.0f} KB"


def count(folder: Path, what: str = "file") -> str:
    n = sum(1 for p in folder.iterdir() if p.is_file())
    return f"{n} {what}{'s' if n != 1 else ''}"


def _board(ctx: Context) -> str:
    assert ctx.board is not None
    return str(ctx.board)


def _fresh(folder: Path) -> None:
    """An empty folder: a re-run into the same output folder must not accumulate exports."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)


def _work(ctx: Context) -> Path:
    """The per-project work folder; a dry run names it without creating it."""
    if not ctx.run.dry_run:
        ctx.plan.work_dir.mkdir(parents=True, exist_ok=True)
    return ctx.plan.work_dir


# ---------------------------------------------------------------------------
# Image helpers (the same geometry as bac_cad_preview.image)
# ---------------------------------------------------------------------------


def crop_pad_square_resize_rgba(
    img: Image.Image, target_size: int = RENDER_WEBP_SIZE, pad_frac: float = RENDER_PAD_FRAC
) -> Image.Image:
    """Crop to the content, pad by ``pad_frac`` of each extent, square up, resize."""
    img = img.convert("RGBA")
    bbox = img.getbbox()
    if not bbox:
        raise ValueError("Image is empty (fully transparent)")
    left, upper, right, lower = bbox
    pad_x, pad_y = int((right - left) * pad_frac), int((lower - upper) * pad_frac)
    img = img.crop(
        (max(0, left - pad_x), max(0, upper - pad_y), min(img.width, right + pad_x), min(img.height, lower + pad_y))
    )
    side = max(img.width, img.height)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return square.resize((target_size, target_size), Image.LANCZOS)


def write_webp(img: Image.Image, path: Path) -> None:
    """Lossless WebP, as ``cwebp -z 9`` produced; written beside the target and renamed into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    img.save(tmp, format="WEBP", lossless=True, quality=100, method=WEBP_METHOD)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def stage_qr(ctx: Context) -> str:
    """Copy the project into the work folder and replace the marker boxes on the copy."""
    plan = ctx.plan
    data = substitute_variables(ctx.qr_text, plan.project.pcb_title.variables())
    if not data:
        raise ConfigError("The QR stage needs a text to encode.", "Pass --qr TEXT or set text in [qr] of the config.")
    if ctx.run.dry_run:
        return f"encodes {data!r}"
    target = plan.qr_board.parent
    if target.exists():
        shutil.rmtree(target)
    try:
        shutil.copytree(plan.project.kicad_dir, target, ignore=COPY_IGNORE)
        n, smallest = insert_qr_file(plan.qr_board, ctx.settings.qr_marker, data)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)  # later stages must export the project itself
        raise
    ctx.board = plan.qr_board
    note = f"{n} marker{'s' if n != 1 else ''}, encodes {data!r}"
    if smallest < QR_MODULE_MIN_MM:
        note += f", modules {smallest:.2f} mm – under the usual {QR_MODULE_MIN_MM} mm silkscreen minimum"
    return note


def stage_render(ctx: Context) -> str:
    plan = ctx.plan
    png = _work(ctx) / "render.png"
    png.unlink(missing_ok=True)
    with ctx.spinner("Rendering the board in 3D"):
        ctx.run(
            [
                ctx.tools.kicad_cli, "pcb", "render", "--output", str(png),
                "--width", str(RENDER_PNG_SIZE), "--height", str(RENDER_PNG_SIZE),
                "--rotate", RENDER_ROTATE, "--light-side-elevation", "90", "--zoom", RENDER_ZOOM,
                "--background", "transparent", "--preset", RENDER_PRESET, _board(ctx),
            ]
        )  # fmt: skip
    if ctx.run.dry_run:
        return ""
    if not png.is_file():
        raise ExternalToolError("kicad-cli wrote no render.", str(png))
    plan.render_webp.unlink(missing_ok=True)
    with Image.open(png) as img:
        framed = crop_pad_square_resize_rgba(img)
    write_webp(framed, plan.render_webp)
    png.unlink(missing_ok=True)
    return kb(plan.render_webp)


def stage_schematic(ctx: Context) -> str:
    plan = ctx.plan
    assert plan.project.sch_file is not None
    with ctx.spinner("Exporting the schematic"):
        ctx.run(
            [
                ctx.tools.kicad_cli,
                "sch",
                "export",
                "pdf",
                "--output",
                str(plan.schematic_pdf),
                "--black-and-white",
                str(plan.project.sch_file),
            ]
        )
    return "" if ctx.run.dry_run else kb(plan.schematic_pdf)


def _rasterize(ctx: Context, svg: Path, png: Path, height_px: int) -> None:
    if ctx.tools.raster_is_inkscape:
        cmd = [
            ctx.tools.svg_raster,
            str(svg),
            "--export-type=png",
            f"--export-filename={png}",
            "--export-area-page",
            f"--export-height={height_px}",
        ]
    else:
        cmd = [ctx.tools.svg_raster, "-h", str(height_px), "-o", str(png), str(svg)]
    ctx.run(cmd)


def stage_pinout(ctx: Context) -> str:
    plan = ctx.plan
    work = _work(ctx)
    svg, png = work / "pinout.svg", work / "pinout.png"
    for f in (svg, png):
        f.unlink(missing_ok=True)
    with ctx.spinner("Plotting the pinout"):
        ctx.run(
            [
                ctx.tools.kicad_cli, "pcb", "export", "svg", "--mode-single", "--output", str(svg),
                "--layers", PINOUT_LAYERS, *PINOUT_SVG_ARGS, _board(ctx),
            ]
        )  # fmt: skip
        target_h = int(PINOUT_CANVAS[1] * PINOUT_HEIGHT_FRAC)
        _rasterize(ctx, svg, png, target_h * PINOUT_OVERSAMPLE)
    if ctx.run.dry_run:
        return ""
    with Image.open(png) as img:
        img = img.convert("RGBA")
        bbox = img.getbbox()
        if not bbox:
            raise ExternalToolError("The pinout plot is empty.", str(svg))
        cropped = img.crop(bbox)
        scale = target_h / cropped.height
        resized = cropped.resize(
            (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))), Image.LANCZOS
        )
        canvas = Image.new("RGBA", PINOUT_CANVAS, (0, 0, 0, 0))
        canvas.paste(
            resized, ((PINOUT_CANVAS[0] - resized.width) // 2, (PINOUT_CANVAS[1] - resized.height) // 2), resized
        )
    write_webp(canvas, plan.pinout_webp)
    for f in (svg, png):
        f.unlink(missing_ok=True)
    return kb(plan.pinout_webp)


def _export_bom(ctx: Context, output: Path, fields: str, labels: str, group_by: str) -> None:
    assert ctx.plan.project.sch_file is not None
    ctx.run(
        [
            ctx.tools.kicad_cli, "sch", "export", "bom", "--output", str(output),
            "--fields", fields, "--labels", labels, "--group-by", group_by,
            "--sort-field", "Reference", "--field-delimiter", ",", "--string-delimiter", '"',
            str(ctx.plan.project.sch_file),
        ]
    )  # fmt: skip


def legacy_fields(plan: Plan) -> bool:
    """Whether the project's sheets carry the 0.7-era rating fields – the sign of a legacy schematic."""
    for sheet in plan.project.kicad_dir.glob("*.kicad_sch"):
        try:
            text = sheet.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(f'(property "{name}"' in text for name in LEGACY_FIELDS):
            return True
    return False


def _resolve_lines(ctx: Context, name: str) -> list[bom.BomLine] | None:
    """The resolution export of the schematic as lines; ``None`` in a dry run."""
    lines_csv = _work(ctx) / name
    _export_bom(ctx, lines_csv, bom.RESOLVE_FIELDS, bom.RESOLVE_LABELS, bom.RESOLVE_GROUP_BY)
    if ctx.run.dry_run:
        return None
    if not lines_csv.is_file():
        raise ExternalToolError("kicad-cli wrote no BOM to resolve.", str(lines_csv))
    return bom.read_export(lines_csv)


def stage_bom(ctx: Context) -> str:
    """The plain export with the scheme's columns; thin with a catalog also the dev, flight, JLCPCB and issues files."""
    plan, s = ctx.plan, ctx.settings
    fields, labels, group_by = s.bom_columns(ctx.scheme)
    _export_bom(
        ctx,
        plan.bom_csv,
        f"{fields},{bom.PER_FOOTPRINT}",
        f"{labels},{bom.PER_FOOTPRINT}",
        f"{group_by},{bom.PER_FOOTPRINT}",
    )
    if not ctx.run.dry_run:
        if not plan.bom_csv.is_file():
            raise ExternalToolError("kicad-cli wrote no BOM.", str(plan.bom_csv))
        bom.fold_per_footprint(plan.bom_csv, fields)
    if ctx.scheme == "legacy":
        return "legacy scheme" if ctx.run.dry_run else f"{kb(plan.bom_csv)}, legacy scheme"
    if ctx.catalog is None:
        return "" if ctx.run.dry_run else kb(plan.bom_csv)
    lines = _resolve_lines(ctx, "bom-resolve.csv")
    if lines is None:
        return "with dev, flight, jlcpcb and issues"
    summary = bom.write_builds(
        ctx.catalog,
        lines,
        {grade: plan.bom_build_csv(grade) for grade in ("dev", "flight")},
        plan.bom_jlcpcb_csv,
        plan.bom_issues_csv,
    )
    ctx.shown = f"{plan.sch_base}-bom{{,-dev,-flight,-jlcpcb,-issues}}.csv"
    return summary.note()


def ibom_python(ctx: Context) -> str:
    """The first interpreter that imports ``pcbnew``: the configured one, then the system python."""
    candidates = [c for c in (ctx.settings.ibom_python, "/usr/bin/python3", shutil.which("python3")) if c]
    for py in candidates:
        if ctx.run.ok([py, "-c", "import pcbnew"]):
            return py
    raise ExternalToolError(
        "No Python interpreter imports pcbnew.",
        "The iBOM plugin needs KiCad's Python; set python in [ibom] of the config.",
    )


def stage_ibom(ctx: Context) -> str:
    plan, s = ctx.plan, ctx.settings
    assert plan.project.sch_file is not None
    if s.ibom_script is None:
        raise ConfigError(
            "The iBOM stage needs the plugin path.",
            "Run --init with KiCad's InteractiveHtmlBom plugin installed, or set script in [ibom].",
        )
    if not s.ibom_script.is_file() and not ctx.run.dry_run:
        raise ConfigError(f"iBOM script not found: {s.ibom_script}", "Check script in [ibom] of the config.")
    py = ibom_python(ctx)
    netlist = _work(ctx) / "ibom-netlist.xml"
    # The plugin takes --dest-dir relative to the board's folder, so both paths go in absolute.
    browser = () if ctx.open else ("--no-browser",)
    with ctx.spinner("Building the interactive BOM"):
        ctx.run(
            [
                ctx.tools.kicad_cli,
                "sch",
                "export",
                "netlist",
                "--output",
                str(netlist),
                "--format",
                "kicadxml",
                str(plan.project.sch_file),
            ]
        )
        ctx.run(
            [
                py, str(s.ibom_script), "--dest-dir", str(plan.out_dir.resolve()),
                "--name-format", plan.ibom_html.stem, "--dark-mode", "--highlight-pin1", "selected",
                "--netlist-file", str(netlist.resolve()), *browser, _board(ctx),
            ]
        )  # fmt: skip
    if ctx.run.dry_run:
        return ""
    if not plan.ibom_html.is_file():
        raise ExternalToolError("The iBOM plugin wrote no HTML file.", str(plan.ibom_html))
    return kb(plan.ibom_html)


def _commit(kicad_dir: Path) -> str:
    """The short hash of the project's git commit, with ``+`` when the tree is dirty; ``unknown`` without git."""
    git = shutil.which("git")
    if not git:
        return "unknown"
    try:
        head = subprocess.run(
            [git, "-C", str(kicad_dir), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=30
        )
        if head.returncode != 0:
            return "unknown"
        dirty = subprocess.run(
            [git, "-C", str(kicad_dir), "status", "--porcelain", "--", "."], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return head.stdout.strip() + ("+" if dirty.stdout.strip() else "")


def stage_freeze(ctx: Context) -> str:
    """The frozen project of ``--freeze``'s build next to the project folder."""
    plan = ctx.plan
    if ctx.scheme == "legacy":
        raise ConfigError("A legacy-scheme project cannot be frozen.", "Its symbols carry their parts already.")
    if ctx.catalog is None:
        raise ConfigError("The freeze stage needs the part catalogs.", "Set passives, ics and other in [catalog].")
    target = target_dir(plan.project.kicad_dir, plan.project.stem, ctx.freeze)
    ctx.shown = f"{target.name}/"
    lines = _resolve_lines(ctx, "bom-freeze.csv")
    if lines is None:
        return f"{ctx.freeze} build"
    with ctx.spinner("Freezing the project"):
        resolved = [resolve(ctx.catalog, line, ctx.freeze) for line in lines]
        frozen = freeze_project(
            plan.project.kicad_dir,
            target,
            build=ctx.freeze,
            resolved=resolved,
            catalog=ctx.catalog,
            commit=_commit(plan.project.kicad_dir),
            tool=f"{TOOL_NAME} {__version__}",
        )
    return frozen.note()


def stage_gerbers(ctx: Context) -> str:
    plan = ctx.plan
    layers = [*plan.project.copper, *GERBER_LAYERS, *(PANEL_LAYERS if plan.project.panel else ())]
    if not ctx.run.dry_run:
        _fresh(plan.gerber_dir)
    with ctx.spinner("Plotting Gerbers"):
        ctx.run(
            [
                ctx.tools.kicad_cli, "pcb", "export", "gerbers", "--output", str(plan.gerber_dir),
                "--layers", ",".join(layers), "--no-x2", "--precision", "6", "--no-protel-ext", _board(ctx),
            ]
        )  # fmt: skip
    if ctx.run.dry_run:
        return f"{len(layers)} layers"
    return count(plan.gerber_dir)


def stage_drills(ctx: Context) -> str:
    plan = ctx.plan
    if not ctx.run.dry_run:
        _fresh(plan.drill_dir)
    ctx.run(
        [
            ctx.tools.kicad_cli, "pcb", "export", "drill", "--output", str(plan.drill_dir),
            "--format", "excellon", "--drill-origin", "absolute", "--excellon-units", "mm",
            "--excellon-zeros-format", "decimal", _board(ctx),
        ]
    )  # fmt: skip
    if ctx.run.dry_run:
        return ""
    return count(plan.drill_dir)


def stage_centroid(ctx: Context) -> str:
    plan = ctx.plan
    if not ctx.run.dry_run:
        _fresh(plan.centroid_dir)
    ctx.run(
        [
            ctx.tools.kicad_cli, "pcb", "export", "pos", "--output", str(plan.centroid_pos), "--format", "ascii",
            "--units", "mm", "--side", "both", "--smd-only", "--exclude-dnp", "--use-drill-file-origin", _board(ctx),
        ]
    )  # fmt: skip
    return "" if ctx.run.dry_run else kb(plan.centroid_pos)


def stage_step(ctx: Context) -> str:
    plan, s = ctx.plan, ctx.settings
    with ctx.spinner("Exporting the STEP model"):
        ctx.run(
            [
                ctx.tools.kicad_cli,
                "pcb",
                "export",
                "step",
                "--output",
                str(plan.step_file),
                "--subst-models",
                "--force",
                _board(ctx),
            ]
        )
    if ctx.run.dry_run:
        return ""
    # KiCad writes placeholders ("Pcbnew", "Kicad") into the header, so the configured values replace them.
    header = set_step_header(
        plan.step_file,
        name=plan.step_file.name,
        author=s.author or None,
        organization=s.organization or None,
        overwrite=True,
    )
    who = ", ".join(
        x
        for x in (header.author[0] if header.author else "", header.organization[0] if header.organization else "")
        if x
    )
    return f"{kb(plan.step_file)}" + (f", {who}" if who else "")


def stage_zip(ctx: Context) -> str:
    """Rename kicad-cli's Gerber and drill names to the scheme, fix the job file, zip the manufacturing set."""
    plan = ctx.plan
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d-%H-%M")
    zip_path = plan.out_dir / f"{plan.base}-{stamp}.zip"
    if ctx.run.dry_run:
        return ""
    broken = sorted(ctx.failed & {"gerbers", "drills", "centroid"})
    if broken:
        raise ExternalToolError(f"Not zipping: {', '.join(broken)} failed.", "Fix the export and run again.")
    ctx.shown = zip_path.name
    stems = [plan.project.pcb_file.stem, plan.project.stem]
    g = normalize_export_names(plan.gerber_dir, stems, plan.base, plan.project.tokens)
    d = normalize_export_names(plan.drill_dir, stems, plan.base, plan.project.tokens)
    rewrite_gbrjob(plan.gerber_dir, g)
    zip_path.unlink(missing_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for sub in (plan.gerber_dir, plan.drill_dir, plan.centroid_dir):
            if not sub.is_dir():
                continue
            for f in sorted(sub.rglob("*")):
                if f.is_file():
                    zf.write(f, arcname=str(f.relative_to(plan.out_dir)))
                    n += 1
    return f"{n} files, {kb(zip_path)}, renamed {len(g)} gerber · {len(d)} drill"


@dataclass(frozen=True)
class Stage:
    name: str
    label: str
    run: Callable[[Context], str]
    output: Callable[[Plan], str]  # what the stage line names
    needs_schematic: bool = False
    opt_in: bool = False  # runs only when asked for (--ibom, --qr)


STAGES: tuple[Stage, ...] = (
    Stage("qr", "QR code", stage_qr, lambda p: f".work/project/{p.project.pcb_file.name}", opt_in=True),
    Stage("render", "Render", stage_render, lambda p: p.render_webp.name),
    Stage("schematic", "Schematic", stage_schematic, lambda p: p.schematic_pdf.name, needs_schematic=True),
    Stage("pinout", "Pinout", stage_pinout, lambda p: p.pinout_webp.name, needs_schematic=True),
    Stage("bom", "BOM", stage_bom, lambda p: p.bom_csv.name, needs_schematic=True),
    Stage("ibom", "iBOM", stage_ibom, lambda p: p.ibom_html.name, needs_schematic=True, opt_in=True),
    Stage(
        "freeze",
        "Freeze",
        stage_freeze,
        lambda p: f"{p.project.stem}-frozen-<build>/",
        needs_schematic=True,
        opt_in=True,
    ),
    Stage("gerbers", "Gerbers", stage_gerbers, lambda p: "gerber/"),
    Stage("drills", "Drills", stage_drills, lambda p: "drill/"),
    Stage("centroid", "Centroid", stage_centroid, lambda p: f"centroid/{p.centroid_pos.name}"),
    Stage("step", "STEP", stage_step, lambda p: p.step_file.name),
    Stage("zip", "Zip", stage_zip, lambda p: f"{p.base}-<YYYY-MM-DD-HH-MM>.zip"),
)
STAGE_NAMES = tuple(s.name for s in STAGES)


def select_stages(only: set[str], skip: set[str], *, ibom: bool, qr: bool, freeze: bool = False) -> list[Stage]:
    """The stages of this run, in order. Opt-in stages run when asked for or named in ``--only``."""
    wanted = {"ibom": ibom, "qr": qr, "freeze": freeze}
    out = []
    for s in STAGES:
        if only and s.name not in only:
            continue
        if s.name in skip:
            continue
        if s.opt_in and not wanted[s.name] and s.name not in only:
            continue
        out.append(s)
    return out
