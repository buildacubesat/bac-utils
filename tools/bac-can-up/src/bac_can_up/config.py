# SPDX-License-Identifier: MIT
"""Settings for the bring-up: which adapter, which interface, which bitrate by default.

The adapter path is machine-specific (it carries the CANable's serial
number), so it lives in ``~/.config/bac/bac-can-up.toml`` rather than in
the repository. ``--init`` writes that file and fills the path in when
exactly one serial adapter is plugged in.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bac_common.config import load_toml, require_setup
from bac_common.errors import ConfigError

TOOL = "bac-can-up"
SERIAL_BY_ID = Path("/dev/serial/by-id")

DEFAULT_INTERFACE = "can0"
DEFAULT_BITRATE = "500k"
DEFAULT_WAIT_TIMEOUT = 5.0

CONFIG_TEMPLATE = """# bac-can-up.toml
# Build a CubeSat – CANable SLCAN bring-up. Machine-specific, so it lives here
# and not in the repository.

[device]
# The adapter's stable path under /dev/serial/by-id/. `bac-can-up --init`
# lists what is plugged in.
path = "{device}"
# SocketCAN interface name slcand creates.
interface = "{interface}"

[defaults]
# Used when no BITRATE is given on the command line: 10k … 1M.
bitrate = "{bitrate}"
# Seconds to wait for the interface to disappear after stopping slcand and
# to appear after starting it.
wait_timeout = {wait_timeout:g}
"""


@dataclass(frozen=True, slots=True)
class Settings:
    device: str
    interface: str = DEFAULT_INTERFACE
    bitrate: str = DEFAULT_BITRATE
    wait_timeout: float = DEFAULT_WAIT_TIMEOUT


def render_template(device: str = "") -> str:
    return CONFIG_TEMPLATE.format(
        device=device, interface=DEFAULT_INTERFACE, bitrate=DEFAULT_BITRATE, wait_timeout=DEFAULT_WAIT_TIMEOUT
    )


def serial_candidates(directory: Path | None = None) -> list[Path]:
    """Every stable serial-adapter path currently present, sorted."""
    directory = directory or SERIAL_BY_ID
    if not directory.is_dir():
        return []
    return sorted(directory.iterdir())


def load_settings(config_path: str | None, *, device_required: bool = True) -> Settings:
    """The config, or the setup message; ``device_required=False`` when ``--device`` supplies the adapter."""
    config = load_toml(TOOL, config_path)
    if device_required:
        require_setup(TOOL, config, "device.path")
    device = config.get("device", {})
    defaults = config.get("defaults", {})
    if not isinstance(device, dict) or not isinstance(defaults, dict):
        raise ConfigError("[device] and [defaults] must be tables.", f"See `{TOOL} --init` for the shape.")
    try:
        wait_timeout = float(defaults.get("wait_timeout", DEFAULT_WAIT_TIMEOUT))
    except (TypeError, ValueError) as exc:
        raise ConfigError("defaults.wait_timeout must be a number of seconds.") from exc
    if wait_timeout <= 0:
        raise ConfigError("defaults.wait_timeout must be positive.")
    return Settings(
        device=str(device.get("path") or ""),
        interface=str(device.get("interface") or DEFAULT_INTERFACE),
        bitrate=str(defaults.get("bitrate") or DEFAULT_BITRATE),
        wait_timeout=wait_timeout,
    )
