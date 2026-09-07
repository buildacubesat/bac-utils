# SPDX-License-Identifier: MIT
"""The bring-up sequence, with the operating system behind a small seam.

``slcand`` turns the CANable's serial port into a SocketCAN interface; the
bitrate is then set on that interface with ``ip link``. A daemon from an
earlier session is stopped first, because two of them on one port leave
the interface in a state that only a replug fixes. All system access goes
through :class:`System` so the sequence can be tested without a CANable,
without ``sudo`` and without waiting.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bac_common.errors import ExternalToolError, UsageError

__all__ = ["RATES", "System", "Step", "Plan", "normalize_bitrate", "format_bitrate", "plan", "bring_up"]

# Supported bit rates in bit/s; the keys are the spellings shown in --help.
RATES: dict[str, int] = {
    "10k": 10_000,
    "20k": 20_000,
    "50k": 50_000,
    "100k": 100_000,
    "125k": 125_000,
    "250k": 250_000,
    "500k": 500_000,
    "800k": 800_000,
    "1M": 1_000_000,
}

POLL_INTERVAL_S = 0.1


def normalize_bitrate(value: str) -> int:
    """``500``, ``500k``, ``500000``, ``1M``, ``1000k`` and ``1000000`` all become 500000 or 1000000."""
    text = value.strip().lower().replace(" ", "")
    if not text:
        raise UsageError("BITRATE is empty.", f"Supported rates: {', '.join(RATES)}.")
    if text.endswith("m"):
        number, factor = text[:-1], 1_000_000
    elif text.endswith("k"):
        number, factor = text[:-1], 1_000
    else:
        number, factor = text, 1
    try:
        bps = int(number) * factor
    except ValueError:
        raise UsageError(f"Unsupported bitrate {value!r}.", f"Supported rates: {', '.join(RATES)}.") from None
    if factor == 1 and bps < 10_000:
        bps *= 1_000  # a bare "500" means 500 kbit/s, as in the original script
    if bps not in RATES.values():
        raise UsageError(f"Unsupported bitrate {value!r}.", f"Supported rates: {', '.join(RATES)}.")
    return bps


def format_bitrate(bps: int) -> str:
    """``500000`` → ``500 kbit/s``, ``1000000`` → ``1 Mbit/s``."""
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:g} Mbit/s"
    return f"{bps // 1_000} kbit/s"


class System:
    """Everything the bring-up asks of the machine; tests replace it."""

    def is_root(self) -> bool:
        return os.geteuid() == 0

    def which(self, program: str) -> str | None:
        return shutil.which(program)

    def device_exists(self, path: str) -> bool:
        return Path(path).exists()

    def interface_present(self, interface: str) -> bool:
        proc = subprocess.run(["ip", "link", "show", interface], capture_output=True, text=True)
        return proc.returncode == 0

    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, errors="replace")

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def monotonic(self) -> float:
        return time.monotonic()


@dataclass(slots=True)
class Step:
    label: str  # what the step achieves, for the ✓ line
    command: list[str]
    ignore_exit: tuple[int, ...] = ()  # exit codes that are not failures (pkill: 1 = nothing to kill)
    wait: str = ""  # "absent" / "present": poll the interface afterwards


@dataclass(slots=True)
class Plan:
    device: str
    interface: str
    bitrate_bps: int
    wait_timeout: float
    steps: list[Step] = field(default_factory=list)
    show: list[str] = field(default_factory=list)  # the final `ip -details link show`


def plan(device: str, interface: str, bitrate_bps: int, wait_timeout: float, *, sudo: bool) -> Plan:
    prefix = ["sudo"] if sudo else []
    steps = [
        Step("Stopped earlier slcand", [*prefix, "pkill", "-x", "slcand"], ignore_exit=(1,), wait="absent"),
        Step("Started slcand", [*prefix, "slcand", "-c", device, interface], wait="present"),
        Step(
            f"Set bitrate {format_bitrate(bitrate_bps)}",
            [*prefix, "ip", "link", "set", "dev", interface, "type", "can", "bitrate", str(bitrate_bps)],
        ),
        Step(f"Brought {interface} up", [*prefix, "ip", "link", "set", "dev", interface, "up"]),
    ]
    return Plan(device, interface, bitrate_bps, wait_timeout, steps, ["ip", "-details", "link", "show", interface])


def _wait_for_interface(system: System, interface: str, expected: str, timeout: float) -> bool:
    deadline = system.monotonic() + timeout
    while True:
        present = system.interface_present(interface)
        if present == (expected == "present"):
            return True
        if system.monotonic() >= deadline:
            return False
        system.sleep(POLL_INTERVAL_S)


def check_prerequisites(system: System, device: str, *, sudo: bool = True) -> None:
    programs = ("slcand", "ip", "sudo") if sudo else ("slcand", "ip")
    for program in programs:
        if system.which(program) is None:
            raise ExternalToolError(
                f"{program} is not installed.",
                "slcand ships with can-utils, ip with iproute2 (`sudo apt install can-utils iproute2`).",
            )
    if not system.device_exists(device):
        raise ExternalToolError(
            f"CANable device not found: {device}",
            "Is it plugged in? `bac-can-up --init` lists the serial adapters present.",
        )


def bring_up(p: Plan, system: System, report: Callable[[str], None]) -> str:
    """Run every step of the plan; returns the final ``ip -details link show`` text.

    ``report`` is called with each completed step's label. Raises
    :class:`ExternalToolError` on the first command that fails or when the
    interface does not appear or disappear within the timeout.
    """
    for step in p.steps:
        proc = system.run(step.command)
        if proc.returncode != 0 and proc.returncode not in step.ignore_exit:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise ExternalToolError(
                f"{' '.join(step.command)} failed (exit {proc.returncode}).", detail[-1] if detail else None
            )
        if step.wait and not _wait_for_interface(system, p.interface, step.wait, p.wait_timeout):
            verb = "disappear after stopping slcand" if step.wait == "absent" else "appear after starting slcand"
            raise ExternalToolError(f"{p.interface} did not {verb} within {p.wait_timeout:g} s.")
        report(step.label)
    proc = system.run(p.show)
    return (proc.stdout or "").rstrip()
