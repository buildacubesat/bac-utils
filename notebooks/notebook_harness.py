# SPDX-License-Identifier: MIT
"""Headless helpers for the engineering notebooks: run a notebook with `app.run()`,
optionally with a profile swapped in for the upload element.

Every notebook of the class reads its profile through `ui_profile.contents()` in
one parse cell and names it through `ui_profile.name()`. The headless path has no
browser to upload a file, so `run(path, profile_toml=...)` rewrites those two
expressions on a temporary copy and runs that instead. Nothing else in the file
is touched, so the numbers are the notebook's own.

`app.run()` returns `(outputs, defs)`: the outputs are the cells' Html objects,
`defs` holds every non-underscore name the cells define.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path
from types import ModuleType

NOTEBOOKS = Path(__file__).resolve().parent

_RAW = re.compile(r"_raw = ui_profile\.contents\(\)[^\n]*")
_NAME = re.compile(r"ui_profile\.name\(\)")


def notebook_path(name: str) -> Path:
    """`notebook_path("bac_link_budget")` → `notebooks/bac-link-budget/bac_link_budget.py`."""
    return NOTEBOOKS / name.replace("_", "-") / f"{name}.py"


def load_module(path: Path) -> ModuleType:
    """Import a notebook file as a module without running its cells.

    The module stays registered in `sys.modules` under a unique key so that anything
    inside the notebook that looks itself up by module name works during `app.run()`;
    `run()` unregisters it afterwards. No bytecode is written for the file.
    """
    key = f"nb_{abs(hash(str(path)))}_{id(path)}"
    spec = importlib.util.spec_from_file_location(key, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(key, None)
        raise
    finally:
        sys.dont_write_bytecode = before
    return module


def with_profile(source: str, profile_toml: str, name: str = "test-profile.toml") -> str:
    """Return the notebook source with the upload element replaced by the given profile bytes."""
    literal = repr(profile_toml.encode("utf-8"))
    # function replacements: re.sub would otherwise interpret the escapes inside the literal
    patched, n_raw = _RAW.subn(lambda _m: f"_raw = {literal}", source, count=1)
    if n_raw != 1:
        raise ValueError("no `_raw = ui_profile.contents()` line to patch")
    return _NAME.sub(lambda _m: repr(name), patched)


def run(path: Path | str, profile_toml: str | None = None) -> tuple[ModuleType, object, dict]:
    """`app.run()` on the notebook at `path`; with `profile_toml`, on a patched copy. Returns (module, outputs, defs)."""
    path = Path(path)
    tmp_path: Path | None = None
    if profile_toml is not None:
        patched = with_profile(path.read_text(encoding="utf-8"), profile_toml)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(patched)
        tmp_path = Path(tmp.name)
    try:
        module = load_module(tmp_path or path)
        try:
            outputs, defs = module.app.run()
        finally:
            sys.modules.pop(module.__name__, None)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
    return module, outputs, dict(defs)
