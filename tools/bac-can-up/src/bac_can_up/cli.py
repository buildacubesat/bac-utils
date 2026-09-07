# SPDX-License-Identifier: MIT
"""bac-can-up – bring up the CANable SLCAN interface for bench testing.

Stops a stale ``slcand``, starts a fresh one on the configured adapter,
sets the bitrate and brings the SocketCAN interface up, then shows it. The
adapter path is machine-specific and comes from
``~/.config/bac/bac-can-up.toml`` (``--init`` writes it); ``--dry-run``
prints the commands instead of running them. The privileged steps run
through ``sudo`` unless already root.

Exit codes: 0 interface up, 1 a step failed or the setup is missing,
2 bad arguments.
"""

from __future__ import annotations

from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import default_config_path, write_config

from . import __version__
from .bringup import RATES, System, bring_up, check_prerequisites, format_bitrate, normalize_bitrate, plan
from .config import TOOL, load_settings, render_template, serial_candidates


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Start the CANable SLCAN interface: fresh slcand, bitrate set, interface up.",
        examples=["bac-can-up", "bac-can-up 250k", "bac-can-up 1M --dry-run"],
        env_file=False,
    )
    parser.add_argument(
        "bitrate",
        nargs="?",
        metavar="BITRATE",
        help=f"{', '.join(RATES)}; 500, 500k and 500000 all work (default: config)",
    )
    parser.add_argument(
        "--device", metavar="PATH", default=None, help="serial adapter to use instead of the configured one"
    )
    parser.add_argument(
        "--interface", metavar="NAME", default=None, help="SocketCAN interface name (default: config, can0)"
    )
    args = parser.parse_args(argv)

    if args.init:
        return _init(args.config)

    settings = load_settings(args.config, device_required=not args.device)
    device = args.device or settings.device
    interface = args.interface or settings.interface
    bitrate_bps = normalize_bitrate(args.bitrate or settings.bitrate)
    system = System()
    p = plan(device, interface, bitrate_bps, settings.wait_timeout, sudo=not system.is_root())

    ui.opening(TOOL, __version__, f"Bringing up {ui.path(interface)} at {format_bitrate(bitrate_bps)}.")
    ui.dim(f"adapter {ui.path(device)}")

    if args.dry_run:
        for step in p.steps:
            ui.step(f"Would run {ui.esc(' '.join(step.command))}")
        ui.step(f"Would run {ui.esc(' '.join(p.show))}")
    else:
        check_prerequisites(system, device, sudo=not system.is_root())
        # No spinner here: sudo may prompt for a password on the same line.
        details = bring_up(p, system, ui.ok)
        for line in details.splitlines():
            ui.dim(ui.esc(line))

    ui.summary(
        [("Interface", interface), ("Bitrate", format_bitrate(bitrate_bps)), ("Commands", len(p.steps) + 1)],
        dry_run=args.dry_run,
    )
    return 0


def _init(config_path: str | None) -> int:
    target = Path(config_path).expanduser() if config_path else default_config_path(TOOL)
    candidates = serial_candidates()
    ui.opening(TOOL, __version__, "First-time setup: recording the CANable's serial path.")
    if candidates:
        ui.step("Serial adapters present:")
        for c in candidates:
            ui.dim(ui.path(c))
    else:
        ui.warn("No serial adapters under /dev/serial/by-id – plug the CANable in and run --init again.")
    device = str(candidates[0]) if len(candidates) == 1 else ""
    if write_config(target, render_template(device)):
        ui.ok(f"Wrote {ui.path(target)}" + (" with that adapter" if device else ""))
        if not device:
            ui.step(f"Put the CANable's path into device.path in {ui.path(target)}.")
    else:
        ui.step(f"{ui.path(target)} exists; left unchanged")
    return 0
