# SPDX-License-Identifier: MIT
"""bac-db – the suite's database command.

``migrate`` creates the shared schema and every installed engine's tables
(safe to re-run); ``status`` shows what the database holds; ``import`` and
``export`` move an engine's data between its files and the database. The
connection string comes from ``BAC_DB_DSN`` in ``.env`` – never from the
command line, where it would land in the shell history – and is shown with
host and database only. ``--init`` writes the config and the ``.env``.

Exit codes: 0 done, 1 a runtime error (no database, bad data), 2 bad arguments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from bac_common import cli as bac_cli
from bac_common import config as common_config
from bac_common import ui
from bac_common.errors import UsageError, UserAbort

from . import __version__, config, db, schema
from .dsn import describe

TOOL = "bac-db"

app = typer.Typer(
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    help=(
        "Build a CubeSat – the operations suite's database: create the schema, "
        "import and export engine data, show status."
    ),
    epilog=(
        "\b\n"
        "Examples:\n"
        "  bac-db --init && bac-db migrate\n"
        "  bac-db import pricing ~/bac/ops-data\n"
        "  bac-db export pricing exports/2026-10-07"
    ),
)


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    return bac_cli.run_typer(app, argv, TOOL)


class State:
    """Resolved per invocation; subcommands read it from the Typer context."""

    def __init__(self, config_path: str | None, env_file: str | None) -> None:
        self.config_path = config_path
        self.env_file = env_file
        self._settings: config.Settings | None = None
        self._engines: list[schema.Engine] | None = None

    @property
    def settings(self) -> config.Settings:
        if self._settings is None:
            self._settings = config.load_settings(self.config_path, self.env_file)
        return self._settings

    @property
    def engines(self) -> list[schema.Engine]:
        if self._engines is None:
            self._engines = schema.discover_engines()
        return self._engines

    def connect(self) -> Any:
        settings = self.settings
        config.require_setup(settings)
        return db.connect(config.require_dsn(settings))


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(bac_cli.version_string(TOOL, __version__))
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "-v", "--version", callback=_version_callback, is_eager=True, help="Print version and exit."
    ),
    list_engines: bool = typer.Option(False, "-l", "--list", help="List the installed engines and exit."),
    env_file: str | None = typer.Option(None, "--env-file", metavar="PATH", help="Load this .env (default: nearest)."),
    config_path: str | None = typer.Option(
        None, "--config", metavar="PATH", help="TOML config (default: ~/.config/bac/bac-suite.toml)."
    ),
    init: bool = typer.Option(False, "--init", help="First-time setup: backend, data directory, DSN."),
) -> None:
    state = State(config_path, env_file)
    ctx.obj = state
    if list_engines:
        for engine in state.engines:
            typer.echo(engine.name)
        raise typer.Exit()
    if init:
        _init(state)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# ---------------------------------------------------------------------------
# --init
# ---------------------------------------------------------------------------


def _ask(prompt: str, default: str) -> str:
    answer = ui.console.input(f"  {prompt} [dim]\\[{ui.esc(default)}][/]: ").strip()
    return answer or default


def run_init(config_path: str | None = None, env_file: str | None = None) -> None:
    """The ``--init`` flow, shared with the engines' launchers (``bac-pricing --init``)."""
    _init(State(config_path, env_file))


def _init(state: State) -> None:
    ui.opening(TOOL, __version__, "First-time setup of the operations suite.")
    target = (
        Path(state.config_path).expanduser() if state.config_path else common_config.default_config_path(config.TOOL)
    )
    if target.exists():
        ui.warn(f"{ui.path(target)} exists and is left as it is; delete it to start over.")
        existing = config.load_settings(str(target), state.env_file)
        data_dir, backend = str(existing.data_dir), existing.backend
    else:
        backend = _ask("Backend (postgres or files)", "postgres")
        if backend not in config.BACKENDS:
            raise UsageError(f"Backend must be one of {', '.join(config.BACKENDS)}.")
        data_dir = _ask("Data directory for the CSV/TOML files", "~/bac/ops-data")
        common_config.write_config(target, config.config_template(data_dir, backend))
        ui.ok(f"Wrote {ui.path(target)}")
    data_path = Path(data_dir).expanduser()
    data_path.mkdir(parents=True, exist_ok=True)
    env_path = data_path / ".env"
    if backend == "postgres":
        if env_path.exists():
            ui.warn(f"{ui.path(env_path)} exists and is left as it is.")
        else:
            dsn = _ask("Postgres DSN", "postgresql://bac@localhost:5432/bac")
            common_config.write_env(env_path, config.env_template(dsn))
            ui.ok(f"Wrote {ui.path(env_path)} (mode 600) with {config.DSN_ENV}")
        ui.dim(f"next: bac-db migrate, then bac-db import <engine> {data_dir}")
    else:
        ui.dim(f"files backend: the engines read and write {data_dir} directly; copy an engine's examples/ there")
    ui.summary([("Config", str(target)), ("Data directory", data_dir), ("Backend", backend)])


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@app.command()
def migrate(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="List the tables; change nothing."),
) -> None:
    """Create the shared schema and every engine's tables. Idempotent."""
    state: State = ctx.obj
    engines = state.engines
    ui.opening(TOOL, __version__, "Creating the suite schema.")
    tables = schema.table_names(schema.SHARED_DDL) + [t for e in engines for t in schema.table_names(e.ddl)]
    if dry_run:
        for t in tables:
            ui.step(f"would ensure {ui.path(t)}")
        ui.summary([("Engines", len(engines)), ("Tables", len(tables))], dry_run=True)
        return
    with state.connect() as conn:
        ui.dim(f"database {describe(state.settings.dsn or '')}")
        with ui.spinner("Running the schema scripts"):
            created = schema.migrate(conn, engines)
    for t in created:
        ui.ok(f"{ui.path(t)}")
    ui.summary([("Engines", len(engines)), ("Tables", len(created))])


@app.command()
def status(ctx: typer.Context) -> None:
    """Row counts per table and each engine's own status line."""
    state: State = ctx.obj
    settings = state.settings
    config.require_setup(settings)
    ui.opening(TOOL, __version__, "Database status.")
    if not settings.uses_db:
        ui.warn("Backend is `files`: engines read and write the data directory directly, there is no database.")
        _files_status(state)
        return
    with state.connect() as conn:
        ui.dim(f"database {describe(settings.dsn or '')}")
        rows: list[tuple[str, int | str]] = []
        for table, n in schema.table_counts(conn, schema.SHARED_TABLES).items():
            rows.append((table, n))
        extra: list[tuple[str, object]] = []
        for engine in state.engines:
            for table, n in schema.table_counts(conn, engine.tables).items():
                rows.append((table, n))
            if engine.status:
                extra.extend(engine.status(conn))
    ui.fields(extra)
    ui.summary(rows)


def _files_status(state: State) -> None:
    data_dir = state.settings.data_dir
    ui.fields([("Data directory", str(data_dir))])
    rows: list[tuple[str, int | str]] = []
    for engine in state.engines:
        present = sum(1 for f in engine.files if (data_dir / f).exists())
        rows.append((f"{engine.name} files", f"{present}/{len(engine.files)}"))
    ui.summary(rows)


def _engine(state: State, name: str) -> schema.Engine:
    engine = schema.find_engine(state.engines, name)
    if engine is None:
        known = ", ".join(e.name for e in state.engines) or "none installed"
        raise UsageError(f"Unknown engine '{name}'.", f"Installed engines: {known}.")
    return engine


@app.command("import")
def import_(
    ctx: typer.Context,
    engine_name: str = typer.Argument(..., metavar="ENGINE", help="Engine to import (see -l)."),
    data_dir: Path | None = typer.Argument(
        None, metavar="[DIR]", help="Folder with its data files (default: data directory)."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Replace the engine's tables without asking."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate the files and report; change nothing."),
) -> None:
    """Replace an engine's tables from its data files (asks first).

    Shared items and catalog rows are upserted, never deleted.
    """
    state: State = ctx.obj
    engine = _engine(state, engine_name)
    settings = state.settings
    config.require_setup(settings)
    source = (data_dir or settings.data_dir).expanduser()
    ui.opening(TOOL, __version__, f"Importing the {engine.name} engine's files.")
    ui.fields([("Engine", engine.name), ("Files", str(source))])
    with ui.spinner("Validating the data files"):
        counts = engine.plan(source)  # raises on bad data before anything is touched
    for kind, n in counts.items():
        ui.ok(f"{kind}: {n}")
    appended = [t for t in engine.tables if t not in engine.replaced]
    if dry_run:
        ui.step(f"would replace {', '.join(ui.path(t) for t in engine.replaced)} and upsert the shared tables")
        if appended:
            ui.step(f"would append to {', '.join(ui.path(t) for t in appended)}")
        ui.summary([(k, v) for k, v in counts.items()], dry_run=True)
        return
    with state.connect() as conn:
        ui.dim(f"database {describe(settings.dsn or '')}")
        existing = schema.table_counts(conn, engine.replaced)
        total = sum(existing.values())
        if total:
            ui.warn(
                "This replaces "
                + ", ".join(f"{ui.path(t)} ({n} rows)" for t, n in existing.items())
                + "; shared items and catalog rows are updated in place"
                + (f"; {', '.join(appended)} gets a new version." if appended else ".")
            )
            if not yes:
                answer = ui.console.input("  Replace them? [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    raise UserAbort()
        with ui.spinner("Importing"):
            result = engine.import_files(conn, source)
    ui.summary([(k, v) for k, v in result.items()])


@app.command()
def export(
    ctx: typer.Context,
    engine_name: str = typer.Argument(..., metavar="ENGINE", help="Engine to export (see -l)."),
    out_dir: Path = typer.Argument(..., metavar="DIR", help="Target folder; created if missing."),
    force: bool = typer.Option(False, "--force", help="Overwrite data files that exist in DIR."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report the files; write nothing."),
) -> None:
    """Write an engine's tables as its data files into DIR."""
    state: State = ctx.obj
    engine = _engine(state, engine_name)
    ui.opening(TOOL, __version__, f"Exporting the {engine.name} engine to files.")
    target = out_dir.expanduser()
    if target.exists() and not target.is_dir():
        raise UsageError(f"{target} exists and is not a directory.")
    present = [f for f in engine.files if (target / f).exists()]
    if present and not force:
        raise UsageError(
            f"{target} already holds {', '.join(present)}.",
            "Export into an empty folder, or pass --force to overwrite.",
        )
    if dry_run:
        for f in engine.files:
            ui.step(f"would write {ui.path(target / f)}")
        ui.summary([("Files", len(engine.files))], dry_run=True)
        return
    with state.connect() as conn:
        ui.dim(f"database {describe(state.settings.dsn or '')}")
        with ui.spinner("Exporting"):
            written = engine.export_files(conn, target)
    for f in written:
        ui.ok(f"Wrote {ui.path(target / f)}")
    ui.summary([("Files", len(written))])
