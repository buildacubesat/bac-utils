# SPDX-License-Identifier: MIT
"""Helpers for the bac-suite-db tests: a stub engine and a config writer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bac_suite_db.schema import Engine

STUB_DDL = """
CREATE SCHEMA IF NOT EXISTS stub;
CREATE TABLE IF NOT EXISTS stub.rows (
    id   text PRIMARY KEY,
    note text DEFAULT ''
);
"""


class StubEngine:
    """Records what bac-db asked of it and behaves like a tiny engine with one table and one file."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.engine = Engine(
            name="stub",
            ddl=STUB_DDL,
            tables=("stub.rows",),
            files=("stub-rows.csv",),
            plan=self.plan,
            import_files=self.import_files,
            export_files=self.export_files,
            status=self.status,
            description="a stub",
        )

    def plan(self, data_dir: Path) -> dict[str, int]:
        self.calls.append(("plan", data_dir))
        path = Path(data_dir) / "stub-rows.csv"
        if not path.exists():
            from bac_common.errors import BacError

            raise BacError(f"stub-rows.csv missing in {data_dir}")
        return {"rows": len(path.read_text().splitlines()) - 1}

    def import_files(self, conn: Any, data_dir: Path) -> dict[str, int]:
        self.calls.append(("import", data_dir))
        rows = Path(data_dir).joinpath("stub-rows.csv").read_text().splitlines()[1:]
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stub.rows")
            for line in rows:
                cur.execute("INSERT INTO stub.rows (id, note) VALUES (%s,%s)", tuple(line.split(",")))
        conn.commit()
        return {"rows": len(rows)}

    def export_files(self, conn: Any, out_dir: Path) -> list[str]:
        self.calls.append(("export", out_dir))
        with conn.cursor() as cur:
            cur.execute("SELECT id, note FROM stub.rows ORDER BY id")
            lines = ["id,note"] + [f"{i},{n}" for i, n in cur.fetchall()]
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        Path(out_dir).joinpath("stub-rows.csv").write_text("\n".join(lines) + "\n")
        return ["stub-rows.csv"]

    def status(self, conn: Any) -> list[tuple[str, str]]:
        return [("stub note", "fine")]


def write_suite_config(root: Path, backend: str = "postgres", data_dir: Path | None = None) -> Path:
    data = data_dir or (root / "data")
    data.mkdir(parents=True, exist_ok=True)
    path = root / f"bac-suite-{backend}.toml"
    path.write_text(f'[storage]\nbackend = "{backend}"\ndata_dir = "{data}"\n', encoding="utf-8")
    return path


def write_stub_data(data_dir: Path, rows: int = 3) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    lines = ["id,note"] + [f"r{i},note {i}" for i in range(rows)]
    path = data_dir / "stub-rows.csv"
    path.write_text("\n".join(lines) + "\n")
    return path
