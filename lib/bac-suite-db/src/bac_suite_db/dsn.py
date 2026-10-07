# SPDX-License-Identifier: MIT
"""Connection strings without their password.

A DSN carries a password, so it is never printed as given: :func:`redact`
keeps user, host, port and database and drops the password (in both the URL
and the ``key=value`` form psycopg accepts); :func:`describe` reduces it to
``host:port/database`` for panels and callouts.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = ["redact", "describe", "scrub", "password"]

_KEYWORD = re.compile(r"(\bpassword\s*=\s*)(?:'[^']*'|\S+)")


def _is_url(dsn: str) -> bool:
    return dsn.startswith(("postgresql://", "postgres://"))


def redact(dsn: str) -> str:
    """The DSN with its password removed; everything else as written."""
    dsn = dsn.strip()
    if not _is_url(dsn):
        return _KEYWORD.sub(r"\1<redacted>", dsn)
    parts = urlsplit(dsn)
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, hostinfo = netloc.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}@{hostinfo}" if user else hostinfo
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "password"]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), parts.fragment))


def describe(dsn: str) -> str:
    """``host:port/database`` – the two facts worth showing in a panel."""
    dsn = dsn.strip()
    if not _is_url(dsn):
        fields = dict(re.findall(r"(\w+)\s*=\s*('[^']*'|\S+)", dsn))
        host = fields.get("host", "localhost").strip("'")
        port = fields.get("port", "").strip("'")
        db = fields.get("dbname", "").strip("'")
        return f"{host}{':' + port if port else ''}/{db}"
    parts = urlsplit(dsn)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    host = parts.hostname or query.get("host") or "localhost"
    port = parts.port or query.get("port")
    db = parts.path.lstrip("/") or query.get("dbname", "")
    return f"{host}{':' + str(port) if port else ''}/{db}"


def password(dsn: str) -> str | None:
    """The password the DSN carries, in either form, or ``None``."""
    dsn = dsn.strip()
    if _is_url(dsn):
        parts = urlsplit(dsn)
        if parts.password:
            return parts.password
        value = dict(parse_qsl(parts.query, keep_blank_values=True)).get("password")
        return value or None
    match = _KEYWORD.search(dsn)
    if match:
        return match.group(0).split("=", 1)[1].strip().strip("'") or None
    loose = re.search(r":([^:@/\s]+)@", dsn)  # user:password@host with the scheme forgotten
    return loose.group(1) if loose else None


def scrub(text: str, dsn: str | None) -> str:
    """``text`` with the DSN's password (raw and percent-encoded) replaced – for error messages that quote input."""
    if not dsn:
        return text
    found = password(dsn)  # convention-check: allow H1 – this is the redaction, not a stored secret
    if not found:
        return text
    from urllib.parse import quote, unquote

    out = text
    for form in {found, unquote(found), quote(found, safe="")}:
        if form:
            out = out.replace(form, "<redacted>")
    return out
