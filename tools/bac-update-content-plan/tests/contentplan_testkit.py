# SPDX-License-Identifier: MIT
"""Helpers for the bac-update-content-plan tests: a fake Sheets client and throwaway git repositories."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bac_common import gsheets

SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefg"

VALUES = [
    ["Title", "Channel", "Status", "Notes"],
    ["Why a 1U | not a 3U", "YouTube", "draft", "line one\nline two"],
    ["Unboxing", "Shorts", "", "no status, dropped"],
    ["EPS walkthrough", "YouTube", "published"],
    ["", "", "", ""],
]


class FakeClient:
    """Stands in for ``gsheets.SheetsClient``; records calls."""

    def __init__(self, values=None, error: Exception | None = None):
        self.values = VALUES if values is None else values
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def read_range(self, spreadsheet_id, a1_range):
        self.calls.append((spreadsheet_id, a1_range))
        if self.error:
            raise self.error
        return [list(row) for row in self.values]


def install_fake_client(monkeypatch, client: FakeClient) -> FakeClient:
    monkeypatch.setattr(gsheets.SheetsClient, "from_service_account", classmethod(lambda cls, path, scopes=(): client))
    return client


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=True).stdout.strip()


def make_repo(root: Path, *, branch: str = "main", with_remote: bool = False) -> Path:
    """A repository with one commit on ``branch``; optionally a bare remote named origin."""
    repo = root / "docs"
    repo.mkdir(parents=True)
    git(repo, "init", "--quiet", "--initial-branch", branch)
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("# docs\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "--quiet", "-m", "init")
    if with_remote:
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--quiet", "--bare", str(remote)], check=True)
        git(repo, "remote", "add", "origin", str(remote))
        git(repo, "push", "--quiet", "-u", "origin", branch)
    return repo


def write_setup(root: Path, repo: Path, **overrides: object) -> tuple[Path, Path]:
    """A config TOML and a key file; returns ``(config_path, key_path)``."""
    key = root / "key.json"
    key.write_text(json.dumps({"client_email": "bot@example.iam.gserviceaccount.com"}), encoding="utf-8")
    values = {
        "id": SHEET_ID,
        "range": "'Content Plan'!A:D",
        "title": "Content Plan",
        "repo": str(repo),
        "file": "content/content-plan.md",
        "branch": "main",
        "credentials": str(key),
    }
    values.update(overrides)
    status = values.get("status_column")
    status_line = f'status_column = "{status}"\n' if status is not None else ""
    config = root / "bac-update-content-plan.toml"
    config.write_text(
        f"""[sheet]
id = "{values["id"]}"
range = "{values["range"]}"
title = "{values["title"]}"
{status_line}
[output]
repo = "{values["repo"]}"
file = "{values["file"]}"
branch = "{values["branch"]}"

[credentials]
file = "{values["credentials"]}"
""",
        encoding="utf-8",
    )
    return config, key
