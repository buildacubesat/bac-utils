# SPDX-License-Identifier: MIT
"""Google Sheets through a service account – the reader BAC tools share.

The Google client libraries are an optional extra (``bac-common[gsheets]``)
because most tools never talk to a spreadsheet. Everything that touches
them is imported lazily, so importing this module costs nothing and a
missing extra surfaces as a :class:`~bac_common.errors.ConfigError` with
the install hint, not as an ``ImportError`` inside a tool.

Typical use::

    from bac_common import gsheets

    client = gsheets.SheetsClient.from_service_account(gsheets.credentials_path(config_value))
    rows = client.read_range(sheet_id, "'Content Plan'!A:E")

The service account's e-mail address must have been given access to the
spreadsheet (share it like with a person); a 403 from the API nearly always
means that step was skipped, and the error says so.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .errors import ConfigError, ExternalToolError

__all__ = [
    "CREDENTIALS_ENV",
    "READONLY_SCOPE",
    "SheetsClient",
    "credentials_path",
    "credentials_source",
    "service_account_email",
    "sheet_url",
    "spreadsheet_id",
    "quote_sheet_title",
]

CREDENTIALS_ENV = "BAC_GCP_CREDENTIALS"
"""Environment variable naming the service-account JSON key file."""
READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
_URL_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")


def spreadsheet_id(value: str) -> str:
    """The spreadsheet id from an id or a full ``docs.google.com`` URL.

    Config files and ``--init`` answers accept either; the API wants the id.
    """
    text = value.strip()
    match = _URL_RE.search(text)
    if match:
        return match.group(1)
    if _ID_RE.match(text):
        return text
    raise ConfigError(
        "Not a Google Sheets id or URL.",
        "Paste the sheet's URL or the id between /d/ and /edit in it.",
    )


def sheet_url(spreadsheet_id_: str) -> str:
    """The URL a person opens for ``spreadsheet_id_``."""
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id_}/edit"


def quote_sheet_title(title: str) -> str:
    """A sheet title as it appears in an A1 range: ``'Content Plan'``.

    Titles without spaces or punctuation need no quotes; a quote inside a
    title is doubled, as the Sheets API expects.
    """
    if re.fullmatch(r"[A-Za-z0-9_]+", title):
        return title
    return "'" + title.replace("'", "''") + "'"


def credentials_source(
    configured: str | os.PathLike[str] | None = None, *, configured_as: str = "the tool's config"
) -> tuple[Path, str]:
    """The service-account key path and where it came from: ``BAC_GCP_CREDENTIALS``, else the configured path.

    ``configured_as`` names the configured setting in messages, for example
    ``"[credentials] file"``. The variable wins over the setting by design, so
    a stale value in a ``.env`` above the working directory hides the config;
    every message says which of the two was used. The file must exist.
    Nothing is read here; :meth:`SheetsClient.from_service_account` does that.
    """
    env = os.getenv(CREDENTIALS_ENV)
    if env:
        raw, source = env, CREDENTIALS_ENV
    elif configured:
        raw, source = str(configured), configured_as
    else:
        raise ConfigError(
            "No service-account key configured.",
            f"Set {CREDENTIALS_ENV}=/path/to/key.json in a .env file or the environment, or {configured_as}.",
        )
    path = Path(raw).expanduser()
    if not path.is_file():
        if source == CREDENTIALS_ENV and configured:
            detail = (
                f"{path} – set by {CREDENTIALS_ENV}, which wins over {configured_as}; "
                "check the environment and any .env above the working directory."
            )
        elif source == CREDENTIALS_ENV:
            detail = (
                f"{path} – set by {CREDENTIALS_ENV}; check the environment and any .env above the working directory."
            )
        else:
            detail = f"{path} – set by {configured_as}."
        raise ConfigError("Service-account key not found.", detail)
    return path, source


def credentials_path(
    configured: str | os.PathLike[str] | None = None, *, configured_as: str = "the tool's config"
) -> Path:
    """Where the service-account key is; see :func:`credentials_source`."""
    return credentials_source(configured, configured_as=configured_as)[0]


def service_account_email(key_path: Path) -> str | None:
    """The ``client_email`` of a key file, for telling the user whom to share the sheet with."""
    try:
        data = json.loads(key_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    email = data.get("client_email") if isinstance(data, dict) else None
    return str(email) if email else None


def _import_google() -> tuple[Any, Any, Any]:
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as exc:
        raise ConfigError(
            "The Google Sheets client libraries are not installed.",
            "Install bac-common with the gsheets extra: bac-common[gsheets].",
        ) from exc
    return Credentials, build, HttpError


class SheetsClient:
    """A thin, testable wrapper over the Sheets v4 ``spreadsheets().values()`` resource.

    Construct it from a key file with :meth:`from_service_account`, or hand
    any object with the same call chain to the constructor in tests.
    """

    def __init__(self, service: Any, key_path: Path | None = None) -> None:
        self._service = service
        self.key_path = key_path

    @classmethod
    def from_service_account(cls, key_path: Path, scopes: Sequence[str] = (READONLY_SCOPE,)) -> SheetsClient:
        credentials_cls, build, _ = _import_google()
        try:
            credentials = credentials_cls.from_service_account_file(str(key_path), scopes=list(scopes))
        except (OSError, ValueError) as exc:
            raise ConfigError(f"Service-account key is not usable: {key_path}", str(exc)) from exc
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return cls(service, key_path)

    def read_range(self, spreadsheet_id_: str, a1_range: str) -> list[list[str]]:
        """The cells of ``a1_range`` as strings, one list per row.

        Rows come back as the API sends them: trailing empty cells are
        missing, rows after the last non-empty one are missing. Callers pad.
        """
        try:
            result = self._service.spreadsheets().values().get(spreadsheetId=spreadsheet_id_, range=a1_range).execute()
        except _http_error_class() as exc:
            raise _api_error(exc, spreadsheet_id_, self.key_path) from exc
        except _transport_errors() as exc:
            # A revoked key, clock skew or no network: not an HTTP answer, but an answer all the same.
            reason = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
            raise ExternalToolError("Google Sheets could not be reached.", reason) from exc
        values = result.get("values", []) if isinstance(result, dict) else []
        return [["" if cell is None else str(cell) for cell in row] for row in values]


class _NoError(Exception):
    """Stands in for ``HttpError`` when the Google libraries are not installed (fake services in tests)."""


def _transport_errors() -> tuple[type[Exception], ...]:
    """Auth and transport failures that are not ``HttpError``: ``RefreshError``, ``TransportError``, DNS, sockets."""
    errors: list[type[Exception]] = [OSError]
    try:
        from google.auth.exceptions import GoogleAuthError

        errors.append(GoogleAuthError)
    except ImportError:
        pass
    try:
        from httplib2 import HttpLib2Error

        errors.append(HttpLib2Error)
    except ImportError:
        pass
    return tuple(errors)


def _http_error_class() -> type[Exception]:
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        return _NoError
    return HttpError


def _api_error(exc: Any, spreadsheet_id_: str, key_path: Path | None) -> ExternalToolError:
    status = getattr(getattr(exc, "resp", None), "status", None)
    reason = getattr(exc, "reason", None) or str(exc)
    reason = str(reason).splitlines()[0][:200]
    if status == 403:
        who = service_account_email(key_path) if key_path else None
        hint = f"Share the sheet with {who}." if who else "Share the sheet with the service account's e-mail address."
        return ExternalToolError("Google Sheets refused the request (HTTP 403).", hint)
    if status == 404:
        return ExternalToolError(
            "Google Sheets found no spreadsheet with that id (HTTP 404).", f"Check the id: {spreadsheet_id_}"
        )
    if status == 400:
        return ExternalToolError("Google Sheets rejected the range (HTTP 400).", reason)
    label = f"HTTP {status}" if status else "no response"
    return ExternalToolError(f"Google Sheets request failed ({label}).", reason)
