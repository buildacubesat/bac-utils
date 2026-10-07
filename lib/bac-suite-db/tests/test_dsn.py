# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from bac_suite_db.dsn import describe, redact


@pytest.mark.parametrize(
    ("dsn", "redacted", "described"),
    [
        ("postgresql://bac:s3cret@db.example:5432/bac", "postgresql://bac@db.example:5432/bac", "db.example:5432/bac"),
        ("postgresql://bac@localhost:5432/bac", "postgresql://bac@localhost:5432/bac", "localhost:5432/bac"),
        ("postgresql://localhost/bac", "postgresql://localhost/bac", "localhost/bac"),
        ("postgres://bac:p%40ss@h:1/d?sslmode=require", "postgres://bac@h:1/d?sslmode=require", "h:1/d"),
        (
            "postgresql://postgres:@/postgres?host=/tmp/pg",
            "postgresql://postgres@/postgres?host=%2Ftmp%2Fpg",
            "/tmp/pg/postgres",
        ),
        (
            "postgresql://u@h/d?password=zzz&dbname=d",  # convention-check: allow H1
            "postgresql://u@h/d?dbname=d",
            "h/d",
        ),
        (
            "host=h port=5432 dbname=d user=u password=zzz",
            "host=h port=5432 dbname=d user=u password=<redacted>",
            "h:5432/d",
        ),
        ("dbname=d user=u password='a b'", "dbname=d user=u password=<redacted>", "localhost/d"),
    ],
)
def test_redact_and_describe(dsn, redacted, described):
    assert redact(dsn) == redacted
    assert describe(dsn) == described
    assert "s3cret" not in redact(dsn) and "zzz" not in redact(dsn)


def test_password_and_scrub():
    from bac_suite_db.dsn import password, scrub

    assert password("postgresql://bac:s3cret@h/d") == "s3cret"
    assert password("postgresql://bac@h/d") is None
    assert password("host=h password=zzz dbname=d") == "zzz"
    assert password("bac:s3cret@localhost/bac") == "s3cret"  # the scheme forgotten
    assert password("postgresql://bac:p%40ss@h/d") == "p%40ss"
    text = 'missing "=" after "bac:s3cret@localhost/bac" in connection info string'
    assert (
        scrub(text, "bac:s3cret@localhost/bac")
        == 'missing "=" after "bac:<redacted>@localhost/bac" in connection info string'
    )
    assert scrub("rate p@ss and p%40ss", "postgresql://u:p%40ss@h/d") == "rate <redacted> and <redacted>"
    assert scrub("nothing", None) == "nothing"
    assert scrub("nothing", "postgresql://u@h/d") == "nothing"


def test_connect_never_echoes_the_password():
    pytest.importorskip("psycopg")
    from bac_common.errors import ExternalToolError
    from bac_suite_db.db import connect

    with pytest.raises(ExternalToolError) as info:
        connect("bac:s3cret@localhost/bac")  # a forgotten scheme: psycopg quotes the whole string
    assert "s3cret" not in info.value.message + (info.value.detail or "")
    assert "could not be parsed" in info.value.message
    with pytest.raises(ExternalToolError) as info:
        connect("postgresql://bac:s3cret@127.0.0.1:1/bac")  # nothing listens on port 1
    assert "s3cret" not in info.value.message + (info.value.detail or "")
    assert "127.0.0.1:1/bac" in info.value.message
