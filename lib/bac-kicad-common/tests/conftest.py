# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fixed_terminal(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")


@pytest.fixture
def rules_dir(tmp_path: Path) -> Path:
    d = tmp_path / "rules"
    d.mkdir()
    (d / "00-general.toml").write_text(
        'title = "General"\ntarget = "symbol"\n\n'
        '[[field]]\nname = "Manufacturer"\nvalue = ""\n\n'
        '[[field]]\nname = "Datasheet URL"\nvalue = "https://example.org/${Manufacturer PN}.pdf"\nrequires = ["Manufacturer PN"]\n\n'
        '[[field]]\nname = "Status"\nvalue = "Active"\n',
        encoding="utf-8",
    )
    (d / "10-passives.toml").write_text(
        'title = "Passives"\ntarget = "symbol"\n\n[match]\nreference_prefixes = ["R", "C"]\n\n'
        '[[field]]\nname = "Tolerance"\nvalue = "1%"\n\n'
        '[[field]]\nname = "R Rated Power"\nvalue = "0.1W"\nwhen = { Package = "^0402$" }\noverwrite = true\n\n'
        '[[field]]\nname = "R Rated Power"\nvalue = "0.2W"\nwhen = { Package = "^0603$" }\noverwrite = true\n',
        encoding="utf-8",
    )
    (d / "30-footprints.toml").write_text(
        'title = "Footprints"\ntarget = "footprint"\n\n[match]\nname_regex = ["^R-"]\n\n'
        '[[field]]\nname = "Land Pattern"\nvalue = "IPC-7351 nominal"\nsize = 0.8\nthickness = 0.1\n',
        encoding="utf-8",
    )
    (d / "60-project.toml").write_text(
        'title = "Project"\ntarget = "schematic"\n\n[match]\nreference_regex = ["^R"]\n\n'
        '[[field]]\nname = "Checked By"\nvalue = "MI"\n\n'
        '[[flag]]\nname = "dnp"\nvalue = true\nwhen_reference = "^R9"\n',
        encoding="utf-8",
    )
    return d
