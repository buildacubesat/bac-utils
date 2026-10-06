# SPDX-License-Identifier: MIT
"""A kicad-cli stand-in for the tests: records every command and writes the files the stage expects."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bac_kicad_generate_artifacts.runner import Runner, Tools
from PIL import Image

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SYNTH = FIXTURES / "eps" / "bac-synth-v2" / "kicad10"
PANEL = FIXTURES / "eps" / "bac-synth-panel-v1" / "kicad10"
DSW = FIXTURES / "deployment-switch" / "kicad10"

TOOLS = Tools(kicad_cli="/usr/bin/kicad-cli", svg_raster="/usr/bin/rsvg-convert")

STEP_SAMPLE = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Open CASCADE Model'),'2;1');
FILE_NAME('bac-synth-v2.step','2026-10-06T10:00:00',('Pcbnew'),('Kicad'),'Open CASCADE STEP processor 7.8','KiCad to STEP converter','Unknown');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#7 = PRODUCT('board','board','',(#8));
ENDSEC;
END-ISO-10303-21;
"""


def _arg(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


def _png(path: Path, size: tuple[int, int], box: tuple[int, int, int, int]) -> None:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    img.paste((30, 120, 60, 255), box)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


class FakeRunner(Runner):
    """Writes plausible outputs for every kicad-cli subcommand; ``fail`` names subcommands that exit 1.

    Gerber files are named the way kicad-cli names them: board stem plus the
    layer's display name with dots as underscores (``…-In1_Cu GND.gbr``).
    """

    def __init__(self, *, dry_run: bool = False, fail: set[str] | None = None, pcbnew: bool = True) -> None:
        super().__init__(dry_run=dry_run)
        self.fail = fail or set()
        self.pcbnew = pcbnew
        self.display_names = {"In1.Cu": "In1.Cu GND", "In2.Cu": "In2.Cu PWR", "F.Cu MIX": "F.Cu MIX"}

    def __call__(
        self, cmd: list[str], *, cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(cmd))
        if self.dry_run:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        words = " ".join(cmd[1:4])
        if cmd[1:3] == ["-c", "import pcbnew"]:
            return subprocess.CompletedProcess(
                cmd, 0 if self.pcbnew else 1, "", "" if self.pcbnew else "ModuleNotFoundError"
            )
        for name in self.fail:
            if name in words:
                return self._fail(cmd, check)
        if words.startswith("pcb render"):
            _png(Path(_arg(cmd, "--output")), (2160, 2160), (400, 700, 1700, 1400))
        elif words.startswith("pcb export svg"):
            Path(_arg(cmd, "--output")).write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
        elif Path(cmd[0]).name == "rsvg-convert":
            _png(Path(_arg(cmd, "-o")), (3456, 1800), (100, 100, 3300, 1700))
        elif words.startswith("sch export pdf"):
            Path(_arg(cmd, "--output")).write_bytes(b"%PDF-1.4 fake\n")
        elif words.startswith("sch export bom"):
            Path(_arg(cmd, "--output")).write_text("#,Designator,Qty\n1,R1 R2,2\n")
        elif words.startswith("sch export netlist"):
            Path(_arg(cmd, "--output")).write_text("<export/>")
        elif words.startswith("pcb export gerbers"):
            out = Path(_arg(cmd, "--output"))
            out.mkdir(parents=True, exist_ok=True)
            stem = Path(cmd[-1]).stem
            files = []
            for layer in _arg(cmd, "--layers").split(","):
                shown = self.display_names.get(layer, layer).replace(".", "_")
                files.append(f"{stem}-{shown}.gbr")
                (out / files[-1]).write_text(f"G04 {layer}*\n")
            job = {
                "Header": {"GenerationSoftware": {"Vendor": "KiCad"}},
                "FilesAttributes": [{"Path": f, "FileFunction": "Copper"} for f in files],
            }
            (out / f"{stem}-job.gbrjob").write_text(json.dumps(job, indent=2))
        elif words.startswith("pcb export drill"):
            out = Path(_arg(cmd, "--output"))
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{Path(cmd[-1]).stem}.drl").write_text("M48\n")
        elif words.startswith("pcb export pos"):
            p = Path(_arg(cmd, "--output"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("### Module positions\n")
        elif words.startswith("pcb export step"):
            out = Path(_arg(cmd, "--output"))
            if out.exists() and "--force" not in cmd:
                return self._fail(cmd, check, "Error: output file already exists")
            out.write_text(STEP_SAMPLE)
        elif "generate_interactive_bom" in cmd[1]:
            dest = Path(_arg(cmd, "--dest-dir"))
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{_arg(cmd, '--name-format')}.html").write_text("<html>ibom</html>")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def _fail(
        self, cmd: list[str], check: bool, message: str = "Error: something kicad-cli says"
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.CompletedProcess(cmd, 1, "", message + "\n")
        if check:
            from bac_common.errors import ExternalToolError

            raise ExternalToolError(f"{Path(cmd[0]).name} failed (exit 1): {message}", " ".join(cmd[1:4]))
        return result

    def subcommands(self) -> list[str]:
        return [" ".join(c[1:4]) if Path(c[0]).name == "kicad-cli" else Path(c[0]).name for c in self.commands]
