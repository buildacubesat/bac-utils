# SPDX-License-Identifier: MIT
"""Bootstrap configuration: the settings a tool needs before it can reach the database.

Two files, both created by ``bac-db --init``:

* ``~/.config/bac/bac-suite.toml`` – the backend (``postgres`` or ``files``)
  and the data directory that holds the CSV/TOML files (import source,
  export target, and the working set in files mode).
* ``.env`` with ``BAC_DB_DSN`` – the connection string, because it carries a
  password. It is looked for in the usual places (``--env-file``, then the
  nearest ``.env`` above the working directory) and, failing those, in the
  data directory, so a notebook launched from anywhere still finds it.

Operational parameters (margins, FX rates, tiers) are not here: they live
in the database as versioned rows, per the suite concept §3.3.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from bac_common import config as common_config
from bac_common.errors import ConfigError

__all__ = [
    "TOOL",
    "CONFIG_ENV",
    "DSN_ENV",
    "DATA_DIR_ENV",
    "BACKENDS",
    "Settings",
    "load_settings",
    "require_setup",
    "require_dsn",
    "config_template",
    "env_template",
]

TOOL = "bac-suite"
CONFIG_ENV = "BAC_SUITE_CONFIG"
"""Overrides the config path – how the launchers hand ``--config`` to a marimo subprocess."""
DSN_ENV = "BAC_DB_DSN"
DATA_DIR_ENV = "BAC_DATA_DIR"
BACKENDS = ("postgres", "files")


@dataclass(frozen=True, slots=True)
class Settings:
    backend: str
    data_dir: Path
    dsn: str | None
    config_path: Path
    env_path: Path | None

    @property
    def uses_db(self) -> bool:
        return self.backend == "postgres"


def load_settings(
    config_path: str | os.PathLike[str] | None = None, env_file: str | os.PathLike[str] | None = None
) -> Settings:
    """Resolve backend, data directory and DSN. Missing config is not an error here; see :func:`require_setup`."""
    chosen = config_path or os.environ.get(CONFIG_ENV) or None
    path = Path(chosen).expanduser() if chosen else common_config.default_config_path(TOOL)
    raw = common_config.load_toml(TOOL, chosen)
    storage = raw.get("storage", {})
    if not isinstance(storage, dict):
        raise ConfigError(f"[storage] must be a table in {path}")
    backend = str(common_config.pick(None, storage, "backend", "postgres"))
    if backend not in BACKENDS:
        raise ConfigError(f"storage.backend must be one of {', '.join(BACKENDS)}; got '{backend}' in {path}")
    data_dir = common_config.pick(DATA_DIR_ENV, storage, "data_dir", "")
    data_path = Path(str(data_dir)).expanduser() if data_dir else Path.cwd()
    if not data_path.is_absolute():
        data_path = (path.parent / data_path).resolve()

    env_path = common_config.load_env(env_file)
    fallback = data_path / ".env"
    if not os.environ.get(DSN_ENV) and fallback.is_file() and fallback != env_path:
        # A nearer .env that belongs to another tool must not hide the one --init wrote.
        load_dotenv(fallback)
        if os.environ.get(DSN_ENV):
            env_path = fallback
    dsn = os.environ.get(DSN_ENV) or None
    return Settings(backend=backend, data_dir=data_path, dsn=dsn, config_path=path, env_path=env_path)


def require_setup(settings: Settings) -> None:
    """The config file must exist. ``--init`` creates it."""
    if not settings.config_path.exists():
        raise ConfigError(
            f"{TOOL} is not set up: {settings.config_path} does not exist.",
            "Run `bac-db --init` to choose the backend and the data directory.",
        )


def require_dsn(settings: Settings) -> str:
    """The DSN for the postgres backend, or a clear error naming where it is looked for."""
    if settings.backend != "postgres":
        raise ConfigError(
            "The configured backend is `files`; there is no database to talk to.",
            f'Set storage.backend = "postgres" in {settings.config_path} and {DSN_ENV} in .env.',
        )
    if not settings.dsn:
        raise ConfigError(
            f"{DSN_ENV} is not set.",
            f"Put it in .env (next to your working directory or in {settings.data_dir}) or run `bac-db --init`.",
        )
    return settings.dsn


def config_template(data_dir: str, backend: str = "postgres") -> str:
    return (
        "# Build a CubeSat – business operations suite\n"
        "# Bootstrap settings only: operational parameters live in the database as versioned rows.\n"
        "\n"
        "[storage]\n"
        '# "postgres" (canonical, one shared store for every engine) or "files" (work from the data\n'
        "# directory's CSV/TOML files; no database needed).\n"
        f"backend = {json.dumps(backend)}\n"
        "# Data files: import source, export target, and the working set in files mode.\n"
        f"data_dir = {json.dumps(data_dir)}\n"
    )


def env_template(dsn: str) -> str:
    return (
        "# Build a CubeSat – business operations suite\n"
        "# The connection string carries the password, so it lives here and never in a TOML file.\n"
        f"{DSN_ENV}={dsn}\n"
    )
