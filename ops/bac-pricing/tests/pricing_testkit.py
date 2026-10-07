# SPDX-License-Identifier: MIT
"""Helpers for the bac-pricing tests."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

FIXTURES = Path(__file__).parent / "fixtures"
"""The Dev Kit v1 data as of 2026-07-06 with the SKUs migrated – the regression anchor (CHF 1'138 at batch 25)."""

ROOT, BATCH = "dev_kit_v1", 25


def write_files_config(root: Path, data_dir: Path) -> Path:
    path = root / "bac-suite-files.toml"
    path.write_text(f'[storage]\nbackend = "files"\ndata_dir = "{data_dir}"\n', encoding="utf-8")
    return path


def write_db_config(root: Path, data_dir: Path) -> Path:
    path = root / "bac-suite-postgres.toml"
    path.write_text(f'[storage]\nbackend = "postgres"\ndata_dir = "{data_dir}"\n', encoding="utf-8")
    return path


def load_notebook() -> ModuleType:
    """Import the notebook module fresh (marimo's ``app`` object is rebuilt per import)."""
    from bac_pricing import NOTEBOOK

    spec = importlib.util.spec_from_file_location(f"bac_pricing_notebook_{os.getpid()}_{id(object())}", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_notebook(config_path: Path) -> dict:
    """Run the notebook headless against the given suite config and return its definitions."""
    from bac_suite_db import config

    saved = os.environ.get(config.CONFIG_ENV)
    os.environ[config.CONFIG_ENV] = str(config_path)
    try:
        module = load_notebook()
        _outputs, defs = module.app.run()
    finally:
        if saved is None:
            os.environ.pop(config.CONFIG_ENV, None)
        else:
            os.environ[config.CONFIG_ENV] = saved
    return defs
