# SPDX-License-Identifier: MIT
"""What a KiCad project folder tells us: files, title block, version tag, names.

The naming scheme of every artifact is ``<prefix>-<subsystem>-<name>-<vXrY>``:

* ``prefix`` and the hardware repository name come from the config
  (``bac`` and ``bac-hardware`` by default);
* ``subsystem`` is the folder below the hardware repository on the path to
  the project (``.../bac-hardware/inhibit/deployment-switch/kicad10`` → ``inhibit``);
* ``name`` is the project's own kebab name: the ``.kicad_pro`` stem (or the
  board's) without the prefix and the trailing ``-v<N>`` token, then the
  title block's title, then the parent folder – so ``bac-deployment-switch-v1``
  gives ``deployment-switch``, never a doubled ``bac-inhibit-bac-...``;
* ``vXrY`` is the ``v`` token of the title block's title plus the ``rev``
  field, normalised (``v1`` + ``2`` → ``v1r2``), with an optional patch
  revision appended (``v1r2.1``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from bac_common import sexp
from bac_common.errors import BacError
from bac_common.utils import slugify

__all__ = [
    "ProjectError",
    "TitleBlock",
    "Project",
    "Plan",
    "discover",
    "read_titleblock",
    "extract_v_from_title",
    "normalize_r",
    "make_vr_tag",
    "apply_patch_rev",
    "detect_subsystem",
    "board_name",
    "asset_prefix",
    "copper_layers",
    "layer_file_tokens",
    "normalize_export_names",
    "rewrite_gbrjob",
]


class ProjectError(BacError):
    """The folder is not a usable KiCad project."""


# ---------------------------------------------------------------------------
# Title block and version tags (the pure functions test_parsing covers)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TitleBlock:
    title: str | None = None
    rev: str | None = None
    date: str | None = None
    company: str | None = None
    comments: dict[int, str] = field(default_factory=dict)

    def variables(self) -> dict[str, str]:
        """KiCad's title block variables: ``TITLE``, ``REVISION``, ``ISSUE_DATE``, ``COMPANY``, ``COMMENT1``…"""
        out = {
            "TITLE": self.title or "",
            "REVISION": self.rev or "",
            "ISSUE_DATE": self.date or "",
            "COMPANY": self.company or "",
        }
        for n, text in self.comments.items():
            out[f"COMMENT{n}"] = text
        return out


def read_titleblock(path: Path) -> TitleBlock:
    """The ``(title_block …)`` of a board or schematic. Empty strings count as absent."""
    text, root = sexp.parse_file(path)
    node = root.child("title_block")
    if node is None:
        return TitleBlock()

    def val(head: str) -> str | None:
        child = node.child(head)
        value = child.value(1).strip() if child else ""
        return value or None

    comments: dict[int, str] = {}
    for c in node.children("comment"):
        index, value = c.value(1), c.value(2).strip()
        if index.isdigit() and value:
            comments[int(index)] = value
    return TitleBlock(val("title"), val("rev"), val("date"), val("company"), comments)


def extract_v_from_title(title: str) -> str | None:
    """``EPS Board v1.2`` → ``v1.2``; ``overview`` is not a version."""
    m = re.search(r"(?i)\bv\s*(\d+(?:\.\d+)*)\b", title)
    return f"v{m.group(1)}" if m else None


def normalize_r(rev: str) -> str:
    """``1``, ``r1``, ``R 1`` → ``r1``; anything else becomes a safe ``r-<text>`` or ``r-unknown``."""
    s = rev.strip()
    m = re.match(r"(?i)^r?\s*(\d+)$", s)
    if m:
        return f"r{int(m.group(1))}"
    safe = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return f"r-{safe}" if safe else "r-unknown"


def make_vr_tag(title: str | None, rev: str | None) -> str:
    v = extract_v_from_title(title) if title else None
    r = normalize_r(rev) if rev else None
    if v and r:
        return f"{v}{r}"
    return v or r or "v-unknownr-unknown"


def apply_patch_rev(tag: str, patch: int | None) -> str:
    return tag if patch is None else f"{tag}.{patch}"


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

_VERSION_SUFFIX = re.compile(r"(?i)(?:^|[-_ ])v\d+(?:\.\d+)*(?:r\d+)?$")


def detect_subsystem(kicad_dir: Path, hardware_root: str) -> str | None:
    """The folder below ``hardware_root`` on the project's path, or ``None`` when the path has none."""
    parts = kicad_dir.resolve().parts
    for i, part in enumerate(parts[:-1]):
        if part == hardware_root:
            return parts[i + 1]
    return None


def _strip_prefixes(name: str, prefix: str, subsystem: str | None) -> str:
    low = name.lower()
    if low == prefix.lower() or (subsystem and low == f"{prefix}-{subsystem}".lower()):
        return ""
    for candidate in ((f"{prefix}-{subsystem}-" if subsystem else None), f"{prefix}-"):
        if candidate and low.startswith(candidate.lower()):
            return name[len(candidate) :]
    return name


def board_name(
    kicad_dir: Path, pro_stem: str | None, pcb_stem: str, title: str | None, prefix: str, subsystem: str | None
) -> str:
    """The project's name without prefix and version token. Stem first, title second, folder last."""
    for stem in (pro_stem, pcb_stem):
        if stem:
            candidate = _strip_prefixes(_VERSION_SUFFIX.sub("", stem), prefix, subsystem).strip("-_ ")
            if candidate:
                return candidate
    if title:
        words = re.sub(r"(?i)\bv\s*\d+(?:\.\d+)*\b", " ", title).strip()
        words = re.sub(
            rf"(?i)^{re.escape(prefix)}(?:[-_ ]{re.escape(subsystem)})?\b[-_ ]*"
            if subsystem
            else rf"(?i)^{re.escape(prefix)}\b[-_ ]*",
            "",
            words,
        )
        candidate = slugify(words)
        if candidate:
            return candidate
    return kicad_dir.parent.name


def asset_prefix(prefix: str, subsystem: str | None, name: str = "") -> str:
    """``bac-inhibit-``; ``bac-`` without a subsystem on the path or when the name is the subsystem itself."""
    if not subsystem or name.lower() == subsystem.lower():
        return f"{prefix}-"
    return f"{prefix}-{subsystem}-"


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------

_COPPER_TYPES = {"signal", "power", "mixed", "jumper"}


def _layers(root: sexp.Node) -> list[tuple[str, str, str | None]]:
    """``(canonical, type, user_name)`` for every entry of the board's ``(layers …)`` block."""
    block = root.child("layers")
    if block is None:
        return []
    out = []
    for entry in block.children():
        atoms = entry.atoms()
        if len(atoms) < 3 or not atoms[0].value.lstrip("-").isdigit():
            continue
        canonical, kind = atoms[1].value, atoms[2].value
        user = atoms[3].value if len(atoms) > 3 and atoms[3].quoted else None
        out.append((canonical, kind, user))
    return out


def copper_layers(pcb_text_root: sexp.Node) -> list[str]:
    """Canonical copper layer names in stack order (``F.Cu``, ``In1.Cu``, …, ``B.Cu``); two without a layers block."""
    layers = [name for name, kind, _ in _layers(pcb_text_root) if kind in _COPPER_TYPES]
    return layers or ["F.Cu", "B.Cu"]


# KiCad's default display names where they differ from the canonical layer names.
DEFAULT_LAYER_NAMES = {
    "F.Adhes": "F.Adhesive",
    "B.Adhes": "B.Adhesive",
    "F.SilkS": "F.Silkscreen",
    "B.SilkS": "B.Silkscreen",
    "Dwgs.User": "User.Drawings",
    "Cmts.User": "User.Comments",
    "Eco1.User": "User.Eco1",
    "Eco2.User": "User.Eco2",
    "F.CrtYd": "F.Courtyard",
    "B.CrtYd": "B.Courtyard",
}


_UNSAFE_IN_FILE_NAMES = re.compile(r'[\\/:*?"<>|%.]')


def file_token(layer_name: str) -> str:
    """The token kicad-cli puts into a plot file name: ``.`` and characters a file name cannot carry become ``_``."""
    return _UNSAFE_IN_FILE_NAMES.sub("_", layer_name)


def layer_file_tokens(pcb_text_root: sexp.Node) -> dict[str, str]:
    """Map from the token kicad-cli puts into a plot file name to the token of the layer's default name.

    kicad-cli names a plot after the layer's display name (``B.Cu MIX`` →
    ``…-B_Cu MIX.gbr`` when the designer renamed the layer); the scheme wants
    KiCad's default name (``…-B_Cu.gbr``, ``…-F_Silkscreen.gbr``). Dots
    become underscores in both. Layers with their default name map to themselves.
    """
    out: dict[str, str] = {}
    for canonical, _, user in _layers(pcb_text_root):
        default = file_token(DEFAULT_LAYER_NAMES.get(canonical, canonical))
        out[file_token(canonical)] = default
        out[default] = default
        if user:
            out[file_token(user)] = default
    return out


# ---------------------------------------------------------------------------
# Export renaming
# ---------------------------------------------------------------------------

_LEFTOVER_TOKENS = re.compile(r"(?i)(?<![a-z0-9])(?:v\d+(?:\.\d+)*(?:r\d+)?|r\d+)(?![a-z0-9])")


def normalize_export_names(folder: Path, stems: list[str], target: str, tokens: dict[str, str]) -> dict[str, str]:
    """Rename kicad-cli's ``<stem>-<layer>.<ext>`` files to ``<target>-<layer>.<ext>``.

    ``stems`` are the names kicad-cli may have used (board stem, project
    stem); the longest matching one is removed from the front of the file
    name, never from the middle. The layer token is mapped through ``tokens``
    and spaces become underscores, so a user layer name cannot put a space
    into a Gerber file name. A file whose new name is taken gets ``-2``,
    ``-3``, … before the extension. Returns ``{old name: new name}``.
    """
    renamed: dict[str, str] = {}
    if not folder.is_dir():
        return renamed
    ordered = sorted({s for s in stems if s}, key=len, reverse=True)
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        stem = p.stem
        for s in ordered:
            if stem.lower().startswith(s.lower()):
                stem = stem[len(s) :]
                break
        stem = _LEFTOVER_TOKENS.sub("", stem)
        layer = stem.strip("-_ .")
        layer = tokens.get(layer, layer).replace(" ", "_")
        new_name = f"{target}-{layer}{p.suffix}" if layer else f"{target}{p.suffix}"
        if p.name == new_name:
            continue
        new_path = p.with_name(new_name)
        wanted, n = new_path.stem, 2
        while new_path.exists():
            new_path = p.with_name(f"{wanted}-{n}{p.suffix}")
            n += 1
        p.rename(new_path)
        renamed[p.name] = new_path.name
    return renamed


def rewrite_gbrjob(folder: Path, renamed: dict[str, str]) -> int:
    """Point the ``.gbrjob`` file at the renamed Gerbers. Returns the number of paths rewritten."""
    total = 0
    for job in folder.glob("*.gbrjob"):
        try:
            data = json.loads(job.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        changed = 0
        for entry in data.get("FilesAttributes", []):
            old = entry.get("Path")
            if old in renamed:
                entry["Path"] = renamed[old]
                changed += 1
        if changed:
            job.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        total += changed
    return total


# ---------------------------------------------------------------------------
# Discovery and the plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Project:
    kicad_dir: Path
    pro_file: Path | None
    pcb_file: Path
    sch_file: Path | None  # None: a panel (no schematic in the folder)
    pcb_title: TitleBlock
    sch_title: TitleBlock
    copper: list[str]
    tokens: dict[str, str]

    @property
    def panel(self) -> bool:
        return self.sch_file is None

    @property
    def stem(self) -> str:
        return (self.pro_file or self.pcb_file).stem


def _pick(kicad_dir: Path, suffix: str, preferred_stem: str | None, required: bool) -> Path | None:
    candidates = sorted(p for p in kicad_dir.glob(f"*{suffix}") if not p.name.startswith("."))
    if preferred_stem:
        for c in candidates:
            if c.stem == preferred_stem:
                return c
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        if required:
            raise ProjectError(
                f"No {suffix} file in {kicad_dir.name}/.", "Pass the folder that holds the KiCad project files."
            )
        return None
    names = ", ".join(c.name for c in candidates)
    hint = f"none named {preferred_stem}{suffix}" if preferred_stem else "no .kicad_pro to choose by"
    raise ProjectError(f"Several {suffix} files in {kicad_dir.name}/ and {hint}.", names)


def discover(kicad_dir: Path) -> Project:
    """Read a project folder. A folder without a schematic is a panel."""
    if not kicad_dir.is_dir():
        raise ProjectError("Not a directory.")
    pros = sorted(p for p in kicad_dir.glob("*.kicad_pro") if not p.name.startswith("."))
    pro = pros[0] if len(pros) == 1 else None
    pro_stem = pro.stem if pro else None
    pcb = _pick(kicad_dir, ".kicad_pcb", pro_stem, required=True)
    assert pcb is not None
    sch = _pick(kicad_dir, ".kicad_sch", pro_stem or pcb.stem, required=False)
    _, pcb_root = sexp.parse_file(pcb)
    return Project(
        kicad_dir=kicad_dir,
        pro_file=pro,
        pcb_file=pcb,
        sch_file=sch,
        pcb_title=read_titleblock(pcb),
        sch_title=read_titleblock(sch) if sch else TitleBlock(),
        copper=copper_layers(pcb_root),
        tokens=layer_file_tokens(pcb_root),
    )


@dataclass(frozen=True)
class Plan:
    """Every output path of one project, decided before any stage runs."""

    project: Project
    name: str
    prefix: str  # bac-inhibit-
    pcb_tag: str
    sch_tag: str
    out_dir: Path

    @property
    def base(self) -> str:
        """``bac-inhibit-deployment-switch-v1r1`` – the stem every artifact shares."""
        return f"{self.prefix}{self.name}-{self.pcb_tag}"

    @property
    def sch_base(self) -> str:
        return f"{self.prefix}{self.name}-{self.sch_tag}"

    @property
    def work_dir(self) -> Path:
        return self.out_dir / ".work"

    @property
    def gerber_dir(self) -> Path:
        return self.out_dir / "gerber"

    @property
    def drill_dir(self) -> Path:
        return self.out_dir / "drill"

    @property
    def centroid_dir(self) -> Path:
        return self.out_dir / "centroid"

    @property
    def render_webp(self) -> Path:
        return self.out_dir / f"{self.base}-render.webp"

    @property
    def pinout_webp(self) -> Path:
        return self.out_dir / f"{self.base}-pinout.webp"

    @property
    def schematic_pdf(self) -> Path:
        return self.out_dir / f"{self.sch_base}-schematic.pdf"

    @property
    def bom_csv(self) -> Path:
        return self.out_dir / f"{self.sch_base}-bom.csv"

    @property
    def ibom_html(self) -> Path:
        return self.out_dir / f"{self.base}-ibom.html"

    @property
    def step_file(self) -> Path:
        return self.out_dir / f"{self.base}-model.step"

    @property
    def centroid_pos(self) -> Path:
        return self.centroid_dir / f"{self.base}-centroid.pos"

    @property
    def qr_board(self) -> Path:
        """The board copy the QR stage writes; the stages after it export from this copy."""
        return self.work_dir / "project" / self.project.pcb_file.name


def make_plan(
    project: Project,
    root: Path,
    *,
    prefix: str,
    hardware_root: str,
    pcb_patch: int | None = None,
    sch_patch: int | None = None,
) -> Plan:
    subsystem = detect_subsystem(project.kicad_dir, hardware_root)
    name = board_name(
        project.kicad_dir,
        project.pro_file.stem if project.pro_file else None,
        project.pcb_file.stem,
        project.pcb_title.title,
        prefix,
        subsystem,
    )
    pcb_tag = apply_patch_rev(make_vr_tag(project.pcb_title.title, project.pcb_title.rev), pcb_patch)
    if project.panel:
        sch_tag = pcb_tag
    else:
        sch_tag = apply_patch_rev(make_vr_tag(project.sch_title.title, project.sch_title.rev), sch_patch)
    return Plan(project, name, asset_prefix(prefix, subsystem, name), pcb_tag, sch_tag, root / f"{name}-{pcb_tag}")
