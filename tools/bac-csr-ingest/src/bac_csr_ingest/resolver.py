# SPDX-License-Identifier: MIT
from __future__ import annotations

import mimetypes
import re
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import requests

from .errors import ResolverError
from .models import SourceItem
from .utils import SUPPORTED_EXTENSIONS, is_url, safe_filename, short_hash

# URLs with these extensions are treated as downloadable documents.
# HTML pages are excluded so websites become external links, not snapshots.
URL_DOCUMENT_EXTENSIONS = set(SUPPORTED_EXTENSIONS) - {".html", ".htm"}

DOCUMENT_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/rtf",
    "text/markdown",
    "text/x-markdown",
    "text/plain",
    "text/csv",
    "application/json",
    "application/x-yaml",
    "text/yaml",
}
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# A list file is recognised by extension, or by a header comment on line 1 of
# any text-like file (.txt, .md, or no extension).
LIST_EXTENSION = ".lst"
LIST_HEADER = "# csr-list"
LIST_HEADER_EXTENSIONS = {".txt", ".md", ""}
# `<input> :: hint text` – `::` cannot occur in a URL or a sane path.
HINT_SEPARATOR = "::"

DOWNLOAD_CHUNK = 1024 * 256


def split_hint(line: str) -> tuple[str, str | None]:
    if HINT_SEPARATOR in line:
        head, _, tail = line.partition(HINT_SEPARATOR)
        return head.strip(), (tail.strip() or None)
    return line.strip(), None


def is_list_file(path: Path) -> bool:
    if path.suffix.lower() == LIST_EXTENSION:
        return True
    if path.suffix.lower() not in LIST_HEADER_EXTENSIONS:
        return False
    try:
        with path.open("r", encoding="utf-8") as f:
            return f.readline().strip().lower().startswith(LIST_HEADER)
    except (OSError, UnicodeDecodeError):
        return False


class InputResolver:
    def __init__(self, tempdir: str | Path | TemporaryDirectory[str], notify: Callable[[str], None] | None = None):
        self.tempdir = Path(getattr(tempdir, "name", tempdir))
        self.download_dir = self.tempdir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.notify = notify or (lambda _msg: None)

    def resolve_many(self, inputs: list[str], hint: str | None = None) -> list[SourceItem]:
        seen: set[str] = set()
        items: list[SourceItem] = []
        for raw in inputs:
            for item in self._resolve_one(raw, hint):
                key = item.source_url or str(Path(item.original).expanduser().resolve())
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        return items

    def _resolve_one(self, raw: str, hint: str | None) -> list[SourceItem]:
        raw = raw.strip()
        if not raw:
            return []

        if is_url(raw):
            item = self._resolve_url(raw)
            item.hint = hint
            return [item]

        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise ResolverError(f"Input does not exist: {raw}")

        if path.is_dir():
            return self._resolve_folder(path, hint)

        if is_list_file(path):
            return self._resolve_list_file(path, hint)

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            self.notify(f"Skipping unsupported file: {path}")
            return []

        return [SourceItem(original=str(path), kind="local_file", staged_path=path, hint=hint)]

    def _resolve_folder(self, folder: Path, hint: str | None) -> list[SourceItem]:
        # List files inside folders are skipped, never expanded, to avoid
        # surprising recursive expansion. Name them on the command line instead.
        items: list[SourceItem] = []
        for p in sorted(folder.rglob("*")):
            if not p.is_file():
                continue
            if is_list_file(p):
                self.notify(f"Skipping list file inside folder (pass it explicitly to expand it): {p}")
                continue
            if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            items.append(SourceItem(original=str(p), kind="local_file", staged_path=p, hint=hint))
        return items

    def _resolve_list_file(self, path: Path, batch_hint: str | None) -> list[SourceItem]:
        items: list[SourceItem] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            target, line_hint = split_hint(line)
            if not target:
                raise ResolverError(f"{path}:{line_no}: hint without an input")
            if Path(target).expanduser().resolve() == path:
                raise ResolverError(f"{path}:{line_no}: list file references itself")
            hint = line_hint or batch_hint
            items.extend(self._resolve_one(target, hint))
        return items

    # -- URLs --------------------------------------------------------------

    def _resolve_url(self, url: str) -> SourceItem:
        try:
            with requests.get(url, timeout=60, allow_redirects=True, headers=DEFAULT_HEADERS, stream=True) as response:
                if response.status_code >= 400:
                    return self._external_url_item(
                        url,
                        metadata={
                            "final_url": response.url,
                            "http_status": response.status_code,
                            "note": "Could not fetch URL successfully; treating as external link.",
                        },
                    )

                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                suffix = Path(urlparse(response.url or url).path).suffix.lower()

                if self._is_document_url(suffix, content_type):
                    filename = self._filename_from_response(url, response)
                    target = self.download_dir / filename
                    if target.exists():
                        target = self.download_dir / f"{target.stem}-{short_hash(url)}{target.suffix}"
                    with target.open("wb") as f:
                        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK):
                            f.write(chunk)
                    return SourceItem(
                        original=url,
                        kind="url_document",
                        staged_path=target,
                        source_url=url,
                        metadata={
                            "final_url": response.url,
                            "content_type": content_type,
                            "http_status": response.status_code,
                        },
                    )

                return self._external_url_item(url, metadata=self._metadata_from_html(url, response, content_type))

        except requests.RequestException as exc:
            return self._external_url_item(
                url,
                metadata={"fetch_error": str(exc), "note": "Could not fetch URL; treating as external link."},
            )

    @staticmethod
    def _external_url_item(url: str, metadata: dict | None = None) -> SourceItem:
        return SourceItem(original=url, kind="external_url", source_url=url, metadata=metadata or {})

    @staticmethod
    def _is_document_url(suffix: str, content_type: str) -> bool:
        if suffix in URL_DOCUMENT_EXTENSIONS:
            return True
        if content_type in HTML_CONTENT_TYPES:
            return False
        return content_type in DOCUMENT_CONTENT_TYPES

    def _metadata_from_html(self, url: str, response: requests.Response, content_type: str) -> dict:
        text = response.text if content_type in HTML_CONTENT_TYPES else ""
        return {
            "final_url": response.url,
            "content_type": content_type,
            "http_status": response.status_code,
            "title": self._extract_html_title(text) if text else None,
            "description": self._extract_meta_description(text) if text else None,
        }

    @staticmethod
    def _clean_html_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _extract_html_title(self, text: str) -> str | None:
        match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
        return self._clean_html_text(match.group(1)) if match else None

    def _extract_meta_description(self, text: str) -> str | None:
        patterns = (
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\'][^>]*>',
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\'][^>]*>',
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return self._clean_html_text(match.group(1))
        return None

    @staticmethod
    def _filename_from_response(url: str, response: requests.Response) -> str:
        content_disposition = response.headers.get("content-disposition", "")
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=", 1)[1].strip('" ')
        else:
            filename = Path(urlparse(response.url or url).path).name or f"download-{short_hash(url)}"

        if not Path(filename).suffix:
            content_type = response.headers.get("content-type", "").split(";", 1)[0]
            filename = f"{filename}{mimetypes.guess_extension(content_type) or '.bin'}"

        return safe_filename(filename, Path(filename).suffix or ".bin")
