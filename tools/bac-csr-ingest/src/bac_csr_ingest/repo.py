# SPDX-License-Identifier: MIT
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .blocks import HEADING_RE as _HEADING_LINE_RE
from .blocks import Block, ScanResult, render_block_body, replace_block_body, scan_docs
from .errors import ExternalToolError, PlacementError, SyncError
from .models import BlockTarget, check_rel_md

# Same shape as blocks.HEADING_RE, compiled for whole-text searches.
HEADING_RE = re.compile(_HEADING_LINE_RE.pattern, re.MULTILINE)


def marker_pair(block_id: str) -> str:
    return f"<!-- CSR-RESOURCES:START {block_id} -->\n<!-- CSR-RESOURCES:END {block_id} -->"


class RepoContext:
    def __init__(self, repo_root: Path, docs_path: Path):
        self.repo_root = repo_root
        self.docs_path = docs_path

    # -- reading -----------------------------------------------------------

    def scan(self) -> ScanResult:
        return scan_docs(self.docs_path, self.repo_root)

    def block_targets(self, scan: ScanResult | None = None) -> list[BlockTarget]:
        scan = scan or self.scan()
        return [
            BlockTarget(
                block_id=b.block_id,
                file=b.file,
                heading_context=b.heading_context,
                description=b.description,
            )
            for b in scan.blocks
        ]

    def candidate_sections(self) -> list[dict]:
        sections: list[dict] = []
        for md in sorted(self.docs_path.rglob("*.md")):
            rel = md.relative_to(self.repo_root).as_posix()
            text = md.read_text(encoding="utf-8")
            for match in HEADING_RE.finditer(text):
                level = len(match.group(1))
                if level <= 3:
                    sections.append({"file": rel, "level": level, "title": match.group(2).strip()})
        return sections

    # -- path guard ---------------------------------------------------------

    def require_docs_md(self, value: str | None, *, must_exist: bool) -> str:
        """Validate a markdown path from the classifier against this repository.

        The path must be relative, end in ``.md``, contain no ``..``, and
        resolve inside the docs directory (not merely inside the repository,
        so README.md or files outside ``docs/`` can never be edited). With
        ``must_exist`` the file must already be there – a new block needs a
        parent page. Returns the repo-relative posix path.
        """
        if not value:
            raise PlacementError("Missing Markdown path in placement decision.")
        try:
            rel = check_rel_md(value)
        except ValueError as exc:
            raise PlacementError(f"Refusing Markdown path from placement decision: {exc}") from None
        target = (self.repo_root / rel).resolve()
        docs = self.docs_path.resolve()
        if not target.is_relative_to(docs):
            raise PlacementError(f"Refusing path outside the docs directory: {value}")
        if must_exist and not target.is_file():
            raise PlacementError(f"Parent page does not exist: {value}")
        return rel

    # -- creating blocks and pages ------------------------------------------

    def ensure_block_after_heading(
        self,
        rel_file: str,
        heading: str,
        block_id: str,
        parent_heading: str | None = None,
    ) -> None:
        path = self.repo_root / rel_file
        text = path.read_text(encoding="utf-8")
        if f"CSR-RESOURCES:START {block_id}" in text:
            return

        if parent_heading:
            updated = self._insert_block_under_parent_heading(text, parent_heading, heading, block_id)
            if updated is not None:
                path.write_text(updated, encoding="utf-8")
                return

        heading_pattern = re.compile(rf"^(?P<hashes>#{{1,6}})\s+{re.escape(heading)}\s*$", re.MULTILINE)
        match = heading_pattern.search(text)
        if match:
            insert_at = match.end()
            text = text[:insert_at] + f"\n\n{marker_pair(block_id)}" + text[insert_at:]
        else:
            text = text.rstrip() + f"\n\n## {heading}\n\n{marker_pair(block_id)}\n"
        path.write_text(text, encoding="utf-8")

    def _insert_block_under_parent_heading(
        self,
        text: str,
        parent_heading: str,
        heading: str,
        block_id: str,
    ) -> str | None:
        headings = list(HEADING_RE.finditer(text))
        parent_match = next((m for m in headings if m.group(2).strip() == parent_heading), None)
        if parent_match is None:
            return None

        parent_level = len(parent_match.group(1))
        parent_end = len(text)
        for match in headings:
            if match.start() <= parent_match.start():
                continue
            if len(match.group(1)) <= parent_level:
                parent_end = match.start()
                break

        existing_child = next(
            (m for m in HEADING_RE.finditer(text, parent_match.end(), parent_end) if m.group(2).strip() == heading),
            None,
        )
        if existing_child is not None:
            insert_at = existing_child.end()
            return text[:insert_at] + f"\n\n{marker_pair(block_id)}" + text[insert_at:]

        child_hashes = "#" * min(parent_level + 1, 6)
        block = f"\n\n{child_hashes} {heading}\n\n{marker_pair(block_id)}\n"
        return text[:parent_end].rstrip() + block + text[parent_end:]

    def create_page_with_block(self, rel_file: str, title: str, block_id: str) -> None:
        path = self.repo_root / rel_file
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if f"CSR-RESOURCES:START {block_id}" not in text:
                path.write_text(text.rstrip() + f"\n\n## Resources\n\n{marker_pair(block_id)}\n", encoding="utf-8")
            return
        path.write_text(f"# {title}\n\n{marker_pair(block_id)}\n", encoding="utf-8")

    # -- writing block bodies ----------------------------------------------

    def render_blocks(
        self,
        lines_by_block: dict[str, list[str]],
        indexed_urls_by_block: dict[str, set[str]],
        only: set[str] | None = None,
    ) -> list[str]:
        """Rewrite block bodies from the index. Returns the repo-relative files changed.

        A block is rewritten only when doing so cannot lose information:
        it has no unparsed lines, every URL currently in it is indexed under
        that block id, and its id is unique on the site. Otherwise a
        :class:`SyncError` is raised before any file is touched.
        """
        scan = self.scan()
        if scan.problems:
            p = scan.problems[0]
            raise SyncError(f"{p.file}:{p.line_no}: {p.message}. Run check-blocks.")

        targets = [b for b in scan.blocks if only is None or b.block_id in only]
        if only is not None:
            missing = only - {b.block_id for b in targets}
            if missing:
                raise SyncError(f"Block(s) not found on the site: {', '.join(sorted(missing))}")
        duplicates = scan.duplicate_ids()
        for b in targets:
            self._assert_renderable(b, duplicates, indexed_urls_by_block)

        changed: list[str] = []
        for file, blocks in _group_by_file(targets).items():
            path = self.repo_root / file
            text = path.read_text(encoding="utf-8")
            # Replace bottom-up so earlier line numbers stay valid.
            for b in sorted(blocks, key=lambda b: b.start_line, reverse=True):
                body = render_block_body(lines_by_block.get(b.block_id, []))
                text = replace_block_body(text, b, body)
            if text != path.read_text(encoding="utf-8"):
                path.write_text(text, encoding="utf-8")
                changed.append(file)
        return changed

    @staticmethod
    def _assert_renderable(
        block: Block,
        duplicates: dict[str, list[Block]],
        indexed_urls_by_block: dict[str, set[str]],
    ) -> None:
        where = f"{block.file}:{block.start_line} block '{block.block_id}'"
        if block.block_id in duplicates:
            files = ", ".join(b.file for b in duplicates[block.block_id])
            raise SyncError(f"{where} is defined more than once ({files}); refusing to render.")
        if block.unparsed:
            u = block.unparsed[0]
            raise SyncError(
                f"{where} has {len(block.unparsed)} unparsed line(s), e.g. line {u.line_no}: {u.raw.strip()!r}.",
                "Run sync-blocks.",
            )
        missing = block.urls - indexed_urls_by_block.get(block.block_id, set())
        if missing:
            raise SyncError(
                f"{where} contains {len(missing)} URL(s) not indexed under it, e.g. {sorted(missing)[0]}.",
                "Run sync-blocks.",
            )


def _group_by_file(blocks: list[Block]) -> dict[str, list[Block]]:
    grouped: dict[str, list[Block]] = {}
    for b in blocks:
        grouped.setdefault(b.file, []).append(b)
    return grouped


def git_commit(repo_root: Path, message: str, paths: list[str]) -> bool:
    """Stage exactly ``paths`` and commit. Returns True if a commit was made.

    Deliberately never falls back to broad staging such as ``git add docs``:
    the working tree may contain unrelated manual edits.
    """
    clean_paths = sorted({Path(p).as_posix() for p in paths if str(p).strip()})
    if not clean_paths:
        return False

    try:
        subprocess.run(["git", "add", "--", *clean_paths], cwd=repo_root, check=True)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--", *clean_paths],
            cwd=repo_root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        if not staged:
            return False
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True)
    except FileNotFoundError as exc:
        raise ExternalToolError("git is not installed or not on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise ExternalToolError(
            f"git {exc.cmd[1]} failed with exit code {exc.returncode}.",
            "The index and markdown edits are on disk; commit them by hand or re-run with --no-commit.",
        ) from exc
    return True
