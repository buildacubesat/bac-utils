# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bac_common import gsheets
from bac_common.errors import ConfigError, ExternalToolError

SHEET = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefg"


class FakeValues:
    def __init__(self, result, error=None):
        self.result, self.error, self.calls = result, error, []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return self

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class FakeService:
    def __init__(self, result, error=None):
        self.values_ = FakeValues(result, error)

    def spreadsheets(self):
        return self

    def values(self):
        return self.values_


class FakeHttpError(Exception):
    def __init__(self, status, reason="boom"):
        super().__init__(reason)
        self.resp = type("Resp", (), {"status": status})()
        self.reason = reason


@pytest.fixture
def http_error(monkeypatch):
    monkeypatch.setattr(gsheets, "_http_error_class", lambda: FakeHttpError)
    return FakeHttpError


def test_spreadsheet_id_from_url_and_id():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET}/edit?gid=0#gid=0"
    assert gsheets.spreadsheet_id(url) == SHEET
    assert gsheets.spreadsheet_id(f"  {SHEET}\n") == SHEET
    with pytest.raises(ConfigError):
        gsheets.spreadsheet_id("content plan")


def test_sheet_url_and_quoting():
    assert gsheets.sheet_url(SHEET).endswith(f"/d/{SHEET}/edit")
    assert gsheets.quote_sheet_title("Plan") == "Plan"
    assert gsheets.quote_sheet_title("Content Plan") == "'Content Plan'"
    assert gsheets.quote_sheet_title("Q'n'A") == "'Q''n''A'"


def test_credentials_path_env_wins(tmp_path, monkeypatch):
    key = tmp_path / "key.json"
    key.write_text("{}")
    other = tmp_path / "other.json"
    other.write_text("{}")
    monkeypatch.delenv(gsheets.CREDENTIALS_ENV, raising=False)
    assert gsheets.credentials_path(other) == other
    monkeypatch.setenv(gsheets.CREDENTIALS_ENV, str(key))
    assert gsheets.credentials_path(other) == key


def test_credentials_path_errors(tmp_path, monkeypatch):
    monkeypatch.delenv(gsheets.CREDENTIALS_ENV, raising=False)
    with pytest.raises(ConfigError, match="No service-account key"):
        gsheets.credentials_path(None)
    with pytest.raises(ConfigError, match="not found"):
        gsheets.credentials_path(tmp_path / "missing.json")


def test_service_account_email(tmp_path: Path):
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"client_email": "bot@project.iam.gserviceaccount.com"}))
    assert gsheets.service_account_email(key) == "bot@project.iam.gserviceaccount.com"
    key.write_text("not json")
    assert gsheets.service_account_email(key) is None


def test_read_range_stringifies_and_keeps_ragged_rows():
    service = FakeService({"values": [["Title", "Status"], ["A", 3], [], ["B"]]})
    rows = gsheets.SheetsClient(service).read_range(SHEET, "'Content Plan'!A:E")
    assert rows == [["Title", "Status"], ["A", "3"], [], ["B"]]
    assert service.values_.calls == [{"spreadsheetId": SHEET, "range": "'Content Plan'!A:E"}]


def test_read_range_empty_sheet():
    assert gsheets.SheetsClient(FakeService({})).read_range(SHEET, "A:B") == []


def test_read_range_403_names_the_account(tmp_path, http_error):
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"client_email": "bot@x.iam.gserviceaccount.com"}))
    client = gsheets.SheetsClient(FakeService({}, http_error(403)), key)
    with pytest.raises(ExternalToolError) as info:
        client.read_range(SHEET, "A:B")
    assert "403" in info.value.message
    assert "bot@x.iam.gserviceaccount.com" in (info.value.detail or "")


@pytest.mark.parametrize(("status", "text"), [(404, "no spreadsheet"), (400, "range"), (500, "HTTP 500")])
def test_read_range_other_errors(http_error, status, text):
    client = gsheets.SheetsClient(FakeService({}, http_error(status, "reason line\nmore")))
    with pytest.raises(ExternalToolError) as info:
        client.read_range(SHEET, "A:B")
    assert text in info.value.message
    assert "more" not in (info.value.detail or "")


def test_transport_and_auth_errors_are_reported(monkeypatch):
    from google.auth.exceptions import RefreshError

    for error in (RefreshError("invalid_grant: Invalid JWT Signature.\nmore"), ConnectionError("no route")):
        client = gsheets.SheetsClient(FakeService({}, error))
        with pytest.raises(ExternalToolError) as info:
            client.read_range(SHEET, "A:B")
        assert "could not be reached" in info.value.message
        assert "more" not in (info.value.detail or "")
    assert "invalid_grant" in str(info.value.detail or "") or "no route" in str(info.value.detail or "")


def test_unusable_key_file_is_a_config_error(tmp_path):
    key = tmp_path / "key.json"
    key.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigError, match="not usable") as info:
        gsheets.SheetsClient.from_service_account(key)
    assert "client_email" in (info.value.detail or "")
    key.write_text("not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not usable"):
        gsheets.SheetsClient.from_service_account(key)


def test_missing_extra_is_a_config_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith(("google", "googleapiclient")):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ConfigError, match="not installed") as info:
        gsheets.SheetsClient.from_service_account(Path("key.json"))
    assert "gsheets" in (info.value.detail or "")
