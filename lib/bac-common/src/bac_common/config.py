# SPDX-License-Identifier: MIT
"""Configuration plumbing, following the BAC Project & Tooling Guide §3.6–3.7.

Two layers:

* ``~/.config/bac/<tool>.toml`` – non-secret settings a human edits by hand.
  Loaded with :func:`load_toml`; overridable per run with ``--config PATH``.
* ``.env`` – secrets and machine-specific paths. Loaded with :func:`load_env`
  through python-dotenv; overridable with ``--env-file PATH``.

Environment variables win over TOML values (:func:`pick`), so a CI job or a
one-off shell export can override a setting without editing the file.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from .errors import ConfigError

CONFIG_DIR = Path.home() / ".config" / "bac"

__all__ = [
    "CONFIG_DIR",
    "default_config_path",
    "expand",
    "load_env",
    "load_toml",
    "pick",
    "require_setup",
    "write_config",
    "write_env",
]


def default_config_path(tool: str) -> Path:
    """``~/.config/bac/<tool>.toml``."""
    return CONFIG_DIR / f"{tool}.toml"


def expand(value: str | os.PathLike[str]) -> Path:
    """``~`` and relative paths become absolute paths."""
    return Path(value).expanduser().resolve()


def load_env(env_file: str | os.PathLike[str] | None = None) -> Path | None:
    """Load a ``.env`` file and return its path, or ``None`` when none was found.

    An explicit path must exist. The default search starts in the current
    working directory and walks up – not from this module's own directory,
    which is what python-dotenv would do on its own and which never finds
    anything once the tool is installed into a tool environment.
    """
    if env_file:
        path = Path(env_file).expanduser()
        if not path.exists():
            raise ConfigError(f"Env file does not exist: {path}")
        load_dotenv(path, override=True)
        return path
    found = find_dotenv(usecwd=True)
    if not found:
        return None
    load_dotenv(found)
    return Path(found)


def load_toml(tool: str, config_path: str | os.PathLike[str] | None = None) -> dict:
    """Read the tool's TOML config.

    With no explicit path, a missing default file yields ``{}`` so the caller
    can decide whether setup is required (see :func:`require_setup`). An
    explicit ``--config`` path that does not exist is an error.
    """
    path = Path(config_path).expanduser() if config_path else default_config_path(tool)
    if not path.exists():
        if config_path:
            raise ConfigError(f"Config file does not exist: {path}")
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file is not valid TOML: {path}", str(exc)) from exc


def pick(env_name: str | None, table: Mapping[str, object], key: str, default: object = None) -> object:
    """Environment variable, then TOML table value, then default. Empty strings count as unset."""
    if env_name:
        value = os.getenv(env_name)
        if value:
            return value
    value = table.get(key)
    if value not in (None, ""):
        return value
    return default


def require_setup(tool: str, config: Mapping[str, object], *required: str) -> None:
    """Exit with a clear message when first-time setup has not been run.

    ``required`` are dotted keys (``"source.repo_root"``) that must be present
    and non-empty in ``config``. With no keys given, an empty config is the
    signal. The message directs the user to ``<tool> --init``, as the guide
    requires.
    """
    missing: list[str] = []
    if not required and not config:
        missing.append("configuration")
    for dotted in required:
        node: object = config
        for part in dotted.split("."):
            node = node.get(part) if isinstance(node, Mapping) else None
            if node in (None, ""):
                missing.append(dotted)
                break
    if missing:
        raise ConfigError(
            f"{tool} is not set up: missing {', '.join(missing)}.",
            f"Run `{tool} --init` to create {default_config_path(tool)}.",
        )


def write_config(path: str | os.PathLike[str], text: str, *, overwrite: bool = False) -> bool:
    """Write a config file, creating parent directories. Returns False if it exists and ``overwrite`` is off."""
    target = Path(path).expanduser()
    if target.exists() and not overwrite:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return True


def write_env(path: str | os.PathLike[str], text: str, *, overwrite: bool = False) -> bool:
    """Write a ``.env`` file readable only by the owner. Never overwrites unless asked."""
    target = Path(path).expanduser()
    if target.exists() and not overwrite:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(mode=0o600, exist_ok=True)
    target.chmod(0o600)
    target.write_text(text, encoding="utf-8")
    return True
