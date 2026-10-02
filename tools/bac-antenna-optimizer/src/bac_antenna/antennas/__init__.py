# SPDX-License-Identifier: MIT
"""Antenna types: each turns a parameter dict + config into a solver-independent Model.

Built-ins are registered in BUILTIN. A config can also name a Python file:

    [antenna]
    type = "file:design/model.py"          # module exposing ANTENNA (an AntennaType instance)
    type = "file:design/model.py:MyClass"  # or a class/instance by name

Minimal type:

    class MyAntenna(AntennaType):
        name = "my_antenna"
        params = ("length_mm",)
        def valid(self, p, config): return p["length_mm"] > 0
        def model(self, p, config): ...  # -> Model (see geometry.Model)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from ..config import Config
from ..geometry import Model, Shape

Params = dict[str, float]


class AntennaType:
    """Interface an antenna type implements. Only `name`, `params`, `valid` and `model` are required."""

    name = "antenna"
    params: tuple[str, ...] = ()

    def validate_config(self, config: Config) -> list[str]:
        """Problems with the config's [geometry] section; empty when fine."""
        return []

    def valid(self, p: Params, config: Config) -> bool:
        return True

    def model(self, p: Params, config: Config) -> Model:
        raise NotImplementedError

    # optional: fast estimator for the cavity backend (patches only)
    def shape(self, p: Params, config: Config) -> Shape:
        raise NotImplementedError(f"{self.name} has no cavity-model shape; use --backend coarse for a fast estimate")

    def has_estimator(self) -> bool:
        return type(self).shape is not AntennaType.shape

    # optional: report support (see report.manifest)
    def report_values(self, config: Config, design: dict, options: dict | None = None) -> dict:
        """Per-band template values (design dimensions, ordered length, ...). `options` is the manifest's [boards]."""
        return {}

    def report_globals(self, config: Config, options: dict | None = None) -> dict:
        """Template values shared by all bands (stack, materials, ...)."""
        return {}

    exporters: dict = {}  # name -> ("band" | "once", callable(ctx)); e.g. drawings per band, board files once


def _load_file_type(spec: str):
    path, _, attr = spec.partition(":")
    file = Path(path)
    if not file.exists():
        raise ValueError(f"antenna type file not found: {file}")
    mod_spec = importlib.util.spec_from_file_location(file.stem, file)
    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)
    obj = getattr(module, attr) if attr else getattr(module, "ANTENNA", None)
    if obj is None:
        raise ValueError(f"{file}: define ANTENNA (an AntennaType instance) or name the class with 'file:path:Name'")
    return obj() if isinstance(obj, type) else obj


def builtin_types() -> dict[str, AntennaType]:
    from .dipole import Dipole
    from .patch import AnnularRing, CrossPatch
    from .turnstile import Turnstile

    return {t.name: t for t in (CrossPatch(), AnnularRing(), Dipole(), Turnstile())}


def get_antenna(config: Config) -> AntennaType:
    name = config.antenna_type
    if name.startswith("file:"):
        return _load_file_type(name[5:])
    types = builtin_types()
    try:
        return types[name]
    except KeyError as exc:
        raise ValueError(f"unknown antenna type {name!r}; built-in: {', '.join(types)}; or file:<path.py>") from exc
