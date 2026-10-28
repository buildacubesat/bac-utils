# SPDX-License-Identifier: MIT
"""A throwaway Pages repository with a bare remote, and scripted prompts for `edit`."""

from __future__ import annotations

import subprocess
from pathlib import Path

from bac_page import prompts
from bac_page.redirects import create_redirect

from bac_common import config as config_module


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=True).stdout.strip()


def make_repo(root: Path, *slugs: tuple[str, str]) -> Path:
    """A clone-like repository on `main` with one commit, a bare origin, and the given redirects committed."""
    repo = root / "bac-page"
    repo.mkdir(parents=True)
    git(repo, "init", "--quiet", "--initial-branch", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("# bac.page\n", encoding="utf-8")
    (repo / "cli").mkdir()
    (repo / "cli" / "index.html").write_text("not a redirect\n", encoding="utf-8")
    for slug, target in slugs:
        create_redirect(repo, slug, target)
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "init")
    remote = root / "remote.git"
    subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch", "main", str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "--quiet", "-u", "origin", "main")
    return repo


def write_config(repo: Path) -> Path:
    path = config_module.default_config_path("bac-page")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[repo]\npath = "{repo}"\n', encoding="utf-8")
    return path


def remote_slugs(repo: Path) -> set[str]:
    """The redirect folders in origin/main, as pushed."""
    out = git(repo, "ls-tree", "--name-only", "origin/main")
    return {name for name in out.splitlines() if name not in ("README.md", "cli")}


def script_prompts(monkeypatch, *, pick: int = 0, action: str, text: str = "", confirm: bool = True, qr=None):
    """Replace the InquirerPy prompts of `edit` with fixed answers."""
    monkeypatch.setattr(prompts, "pick_redirect", lambda redirects: pick)
    monkeypatch.setattr(prompts, "pick_action", lambda slug: action)
    monkeypatch.setattr(prompts, "ask_text", lambda message, default: text or default)
    monkeypatch.setattr(prompts, "confirm", lambda message: confirm)
    if qr is not None:
        monkeypatch.setattr(prompts, "qr_options", lambda: qr)
