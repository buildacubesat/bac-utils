# SPDX-License-Identifier: MIT
"""Connections. psycopg is imported late so that the files backend and the tests never need it."""

from __future__ import annotations

from typing import Any

from bac_common.errors import ExternalToolError

from .config import DSN_ENV
from .dsn import describe, scrub

__all__ = ["connect", "ping"]


def connect(dsn: str) -> Any:
    """Open a psycopg connection; a failure names host and database, never the password."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover – psycopg is a dependency; guard for stripped installs
        raise ExternalToolError(
            "psycopg is not installed.", "Reinstall bac-suite-db; psycopg[binary] is a dependency."
        ) from exc
    try:
        return psycopg.connect(dsn)
    except psycopg.ProgrammingError as exc:
        # psycopg quotes the offending string; a forgotten scheme would echo the password
        raise ExternalToolError(
            "The connection string could not be parsed.",
            f"Expected postgresql://user:password@host:5432/database in {DSN_ENV}. ({type(exc).__name__})",
        ) from exc
    except psycopg.Error as exc:
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        raise ExternalToolError(f"Cannot connect to {describe(dsn)}.", scrub(first, dsn)) from exc


def ping(conn: Any) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        return cur.fetchone()[0] == 1
