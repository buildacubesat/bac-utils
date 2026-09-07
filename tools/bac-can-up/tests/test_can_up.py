# SPDX-License-Identifier: MIT
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from bac_can_up import __version__, cli
from bac_can_up.bringup import System, bring_up, check_prerequisites, format_bitrate, normalize_bitrate, plan
from bac_can_up.config import TOOL, load_settings, render_template, serial_candidates

from bac_common import config as config_module
from bac_common.errors import ExternalToolError, UsageError
from bac_common.testing import assert_standard_flags, invoke

DEVICE = "/dev/serial/by-id/usb-Openlight_Labs_CANable2_0000-if00"


class FakeSystem(System):
    """A machine with slcand and ip installed, one CANable, and an interface that follows the commands."""

    def __init__(self, *, root: bool = False, installed=("slcand", "ip", "sudo"), devices=(DEVICE,), failing: str = ""):
        self.root = root
        self.installed = set(installed)
        self.devices = set(devices)
        self.failing = failing  # a program name whose command fails
        self.present = True  # a stale interface from an earlier session
        self.clock = 0.0
        self.commands: list[list[str]] = []
        self.slept = 0.0
        self.stuck = ""  # "absent"/"present": the interface never reaches this state

    def is_root(self) -> bool:
        return self.root

    def which(self, program: str) -> str | None:
        return f"/usr/bin/{program}" if program in self.installed else None

    def device_exists(self, path: str) -> bool:
        return path in self.devices

    def interface_present(self, interface: str) -> bool:
        return self.present

    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        program = command[1] if command[0] == "sudo" else command[0]
        if program == self.failing:
            return subprocess.CompletedProcess(command, 2, "", "RTNETLINK answers: Operation not permitted\n")
        if program == "pkill":
            self.present = self.stuck == "absent"
            return subprocess.CompletedProcess(command, 1, "", "")
        if program == "slcand":
            self.present = self.stuck != "present"
        if program == "ip" and "-details" in command:
            return subprocess.CompletedProcess(
                command, 0, "3: can0: <NOARP,UP,LOWER_UP> mtu 16\n    can state ERROR-ACTIVE\n", ""
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.clock += seconds

    def monotonic(self) -> float:
        return self.clock


def value(stdout: str, label: str) -> str | None:
    m = re.search(rf"{re.escape(label)}\s+:\s+(.+?)\s*$", stdout, re.MULTILINE)
    return m.group(1) if m else None


def write_settings(device: str = DEVICE, **overrides) -> Path:
    target = config_module.CONFIG_DIR / f"{TOOL}.toml"
    text = render_template(device)
    for key, val in overrides.items():
        text = re.sub(rf"^{key} = .*$", f"{key} = {val}", text, flags=re.MULTILINE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


# --- bitrates ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text, bps",
    [
        ("500", 500_000),
        ("500k", 500_000),
        ("500000", 500_000),
        ("1M", 1_000_000),
        ("1m", 1_000_000),
        ("1000", 1_000_000),
    ],
)
def test_normalize_bitrate_accepts_the_three_spellings(text, bps):
    assert normalize_bitrate(text) == bps


def test_normalize_bitrate_accepts_every_supported_rate_and_rejects_others():
    assert (
        normalize_bitrate("10") == 10_000
        and normalize_bitrate("800k") == 800_000
        and normalize_bitrate(" 125K ") == 125_000
    )
    for bad in ("300k", "abc", "", "2M", "9999"):
        with pytest.raises(UsageError) as exc:
            normalize_bitrate(bad)
        assert "Supported rates" in (exc.value.detail or "")


def test_format_bitrate():
    assert format_bitrate(500_000) == "500 kbit/s" and format_bitrate(1_000_000) == "1 Mbit/s"


# --- plan and bring-up --------------------------------------------------------


def test_plan_matches_the_original_script():
    p = plan(DEVICE, "can0", 500_000, 5.0, sudo=True)
    assert [s.command for s in p.steps] == [
        ["sudo", "pkill", "-x", "slcand"],
        ["sudo", "slcand", "-c", DEVICE, "can0"],
        ["sudo", "ip", "link", "set", "dev", "can0", "type", "can", "bitrate", "500000"],
        ["sudo", "ip", "link", "set", "dev", "can0", "up"],
    ]
    assert p.show == ["ip", "-details", "link", "show", "can0"]
    assert plan(DEVICE, "can0", 500_000, 5.0, sudo=False).steps[0].command == ["pkill", "-x", "slcand"]


def test_bring_up_runs_every_step_and_waits_for_the_interface():
    system = FakeSystem()
    labels: list[str] = []
    details = bring_up(plan(DEVICE, "can0", 250_000, 5.0, sudo=True), system, labels.append)
    assert [c[1] for c in system.commands] == ["pkill", "slcand", "ip", "ip", "-details"]
    assert labels == ["Stopped earlier slcand", "Started slcand", "Set bitrate 250 kbit/s", "Brought can0 up"]
    assert details.startswith("3: can0:") and system.slept == 0


def test_bring_up_times_out_when_the_interface_never_appears():
    system = FakeSystem()
    system.stuck = "present"
    with pytest.raises(ExternalToolError, match="did not appear after starting slcand within 5 s"):
        bring_up(plan(DEVICE, "can0", 500_000, 5.0, sudo=True), system, lambda _: None)
    assert system.slept >= 5.0
    system = FakeSystem()
    system.stuck = "absent"
    with pytest.raises(ExternalToolError, match="did not disappear after stopping slcand"):
        bring_up(plan(DEVICE, "can0", 500_000, 2.0, sudo=True), system, lambda _: None)
    assert [c[1] for c in system.commands] == ["pkill"]


def test_bring_up_reports_a_failing_command():
    system = FakeSystem(failing="ip")
    with pytest.raises(ExternalToolError) as exc:
        bring_up(plan(DEVICE, "can0", 500_000, 5.0, sudo=True), system, lambda _: None)
    assert exc.value.message.startswith("sudo ip link set dev can0 type can bitrate 500000 failed (exit 2)")
    assert exc.value.detail == "RTNETLINK answers: Operation not permitted"


def test_prerequisites():
    check_prerequisites(FakeSystem(), DEVICE)
    with pytest.raises(ExternalToolError, match="slcand is not installed"):
        check_prerequisites(FakeSystem(installed=("ip",)), DEVICE)
    with pytest.raises(ExternalToolError, match="sudo is not installed"):
        check_prerequisites(FakeSystem(installed=("slcand", "ip")), DEVICE)
    check_prerequisites(FakeSystem(installed=("slcand", "ip")), DEVICE, sudo=False)
    with pytest.raises(ExternalToolError, match="CANable device not found"):
        check_prerequisites(FakeSystem(devices=()), DEVICE)


# --- config -------------------------------------------------------------------


def test_load_settings_needs_init(tmp_path):
    with pytest.raises(type(ExternalToolError("x")).__mro__[1]) as exc:  # a BacError
        load_settings(None)
    assert "--init" in (exc.value.detail or "")
    write_settings("")
    with pytest.raises(Exception, match="device.path"):
        load_settings(None)


def test_load_settings_reads_overrides():
    write_settings(bitrate='"250k"', interface='"can1"', wait_timeout="2")
    s = load_settings(None)
    assert (s.device, s.interface, s.bitrate, s.wait_timeout) == (DEVICE, "can1", "250k", 2.0)
    write_settings(wait_timeout="0")
    with pytest.raises(Exception, match="positive"):
        load_settings(None)


def test_serial_candidates(tmp_path):
    assert serial_candidates(tmp_path / "missing") == []
    d = tmp_path / "by-id"
    d.mkdir()
    (d / "usb-b").touch()
    (d / "usb-a").touch()
    assert [p.name for p in serial_candidates(d)] == ["usb-a", "usb-b"]


# --- cli ----------------------------------------------------------------------


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_init_records_a_single_adapter(monkeypatch, tmp_path):
    d = tmp_path / "by-id"
    d.mkdir()
    (d / "usb-Openlight_Labs_CANable2_0000-if00").touch()
    monkeypatch.setattr("bac_can_up.config.SERIAL_BY_ID", d)
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0, r.output
    written = config_module.CONFIG_DIR / f"{TOOL}.toml"
    assert f'path = "{d / "usb-Openlight_Labs_CANable2_0000-if00"}"' in written.read_text(encoding="utf-8")
    assert "with that adapter" in r.stdout
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0 and "left unchanged" in r.stdout


def test_init_with_no_or_several_adapters_leaves_the_path_empty(monkeypatch, tmp_path):
    d = tmp_path / "by-id"
    monkeypatch.setattr("bac_can_up.config.SERIAL_BY_ID", d)
    r = invoke(cli._main, ["--init", "--config", str(tmp_path / "c.toml")])
    assert r.exit_code == 0 and "No serial adapters" in r.stdout
    assert 'path = ""' in (tmp_path / "c.toml").read_text(encoding="utf-8")
    d.mkdir()
    (d / "usb-a").touch()
    (d / "usb-b").touch()
    r = invoke(cli._main, ["--init", "--config", str(tmp_path / "d.toml")])
    assert r.exit_code == 0 and "usb-a" in r.stdout and "usb-b" in r.stdout and "Put the CANable" in r.stdout
    assert 'path = ""' in (tmp_path / "d.toml").read_text(encoding="utf-8")


def test_run_without_setup_points_at_init():
    r = invoke(cli._main, [])
    assert r.exit_code == 1 and "not set up" in r.stderr and "--init" in r.stderr


def test_run_brings_the_interface_up(monkeypatch):
    write_settings()
    system = FakeSystem()
    monkeypatch.setattr(cli, "System", lambda: system)
    r = invoke(cli._main, ["250k"])
    assert r.exit_code == 0, r.output
    assert "Bringing up can0 at 250 kbit/s" in r.stdout
    assert "✓ Started slcand" in r.stdout and "✓ Brought can0 up" in r.stdout
    assert "can state ERROR-ACTIVE" in r.stdout
    assert system.commands[2][-1] == "250000" and system.commands[0][0] == "sudo"
    assert value(r.stdout, "Bitrate") == "250 kbit/s" and value(r.stdout, "Commands") == "5"


def test_run_uses_config_default_and_overrides(monkeypatch):
    write_settings(bitrate='"125k"')
    system = FakeSystem(root=True, devices=("/dev/ttyACM3",))
    monkeypatch.setattr(cli, "System", lambda: system)
    r = invoke(cli._main, ["--device", "/dev/ttyACM3", "--interface", "can1"])
    assert r.exit_code == 0, r.output
    write_settings("", bitrate='"125k"')  # --device makes an empty device.path acceptable
    assert invoke(cli._main, ["--device", "/dev/ttyACM3", "--interface", "can1"]).exit_code == 0
    assert system.commands[1] == ["slcand", "-c", "/dev/ttyACM3", "can1"]
    assert system.commands[2][-1] == "125000"


def test_dry_run_prints_commands_and_touches_nothing(monkeypatch):
    write_settings()
    system = FakeSystem(installed=())  # nothing installed: a dry run must not care
    monkeypatch.setattr(cli, "System", lambda: system)
    r = invoke(cli._main, ["1M", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert f"Would run sudo slcand -c {DEVICE} can0" in r.stdout
    assert "Would run sudo ip link set dev can0 type can bitrate 1000000" in r.stdout
    assert "dry run" in r.stdout and system.commands == []


def test_run_fails_cleanly_without_slcand(monkeypatch):
    write_settings()
    system = FakeSystem(installed=("ip",))
    monkeypatch.setattr(cli, "System", lambda: system)
    r = invoke(cli._main, [])
    assert r.exit_code == 1 and "slcand is not installed" in r.stderr and system.commands == []


def test_bad_bitrate_is_a_usage_error():
    write_settings()
    r = invoke(cli._main, ["300k"])
    assert r.exit_code == 2 and "Unsupported bitrate '300k'" in r.stderr


def test_help_fits_eighty_columns(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    assert_standard_flags(cli._main, TOOL, __version__)
