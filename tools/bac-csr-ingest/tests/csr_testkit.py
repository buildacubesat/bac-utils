# SPDX-License-Identifier: MIT
"""Shared fixtures and helpers for the bac-csr-ingest tests."""

from __future__ import annotations

from pathlib import Path

import yaml

EPS_MD = """# EPS

Intro prose with an [inline link](https://example.com/inline) that must be ignored.

## Batteries

### Battery datasheets

<!-- CSR-RESOURCES:START battery-datasheets -->
- **[Panasonic NCR18650B](https://example.com/ncr18650b.pdf)** `PDF` – Cell datasheet
- [Molicel P42A](https://example.com/p42a.pdf) - Manual entry without bold or type
- **[Battery University](https://batteryuniversity.com/)** `Link`
<!-- CSR-RESOURCES:END battery-datasheets -->

## Solar

<!-- CSR-RESOURCES:START solar-cell-datasheets -->
- **[Azur 3G30C](https://example.com/3g30c.pdf)** `PDF` – Triple-junction cell
<!-- CSR-RESOURCES:END solar-cell-datasheets -->
"""

TOOLS_MD = """# Tools

<!-- CSR-RESOURCES:START link-budget-tools -->
- **[AMSAT link budget](https://example.com/linkbudget.xlsx)** `XLSX` – Jan King spreadsheet
<!-- CSR-RESOURCES:END link-budget-tools -->
"""


def write_index(root: Path, records: list[dict]) -> None:
    (root / "data" / "resources.yml").write_text(
        yaml.safe_dump({"resources": records}, sort_keys=False), encoding="utf-8"
    )


def record(url: str, block_id: str, title: str = "T", **kw) -> dict:
    base = {
        "id": "x",
        "title": title,
        "description": "D",
        "file_type": "PDF",
        "url": url,
        "source": url,
        "block_id": block_id,  # legacy field; migrated to block_ids on load
        "sha256": "0" * 64,
        "added": "2026-01-01",
    }
    base.update(kw)
    return base
