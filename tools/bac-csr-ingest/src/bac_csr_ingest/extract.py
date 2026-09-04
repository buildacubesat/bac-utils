# SPDX-License-Identifier: MIT
from __future__ import annotations

import hashlib
from pathlib import Path

from .models import ExtractedDocument, SourceItem
from .utils import sha256_file, strip_markdown_noise

EXCERPT_LIMIT = 16000


class DocumentExtractor:
    def extract(self, item: SourceItem) -> ExtractedDocument:
        if item.kind == "external_url":
            return self._extract_external_url(item)

        if item.staged_path is None:
            raise ValueError("Source item has no staged path")
        path = item.staged_path
        metadata: dict = dict(item.metadata)

        try:
            markdown, extracted_metadata = self._extract_with_docling(path)
            metadata.update(extracted_metadata)
        except Exception as exc:  # docling raises a wide variety of types
            metadata["docling_error"] = str(exc)
            markdown = self._fallback_extract(path)

        title_hint = metadata.get("title") or path.stem.replace("-", " ").replace("_", " ")
        return ExtractedDocument(
            source=item,
            title_hint=title_hint,
            content_excerpt=strip_markdown_noise(markdown, limit=EXCERPT_LIMIT),
            sha256=sha256_file(path),
            extension=path.suffix.lower(),
            size_bytes=path.stat().st_size,
            metadata=metadata,
        )

    def _extract_external_url(self, item: SourceItem) -> ExtractedDocument:
        metadata = dict(item.metadata)
        title_hint = metadata.get("title") or item.source_url or item.original
        final_url = metadata.get("final_url") or item.source_url or item.original
        parts = [
            f"Title: {title_hint}",
            f"URL: {final_url}",
            f"Description: {metadata['description']}" if metadata.get("description") else "",
            f"Content-Type: {metadata['content_type']}" if metadata.get("content_type") else "",
            "This is an external web link. Do not upload it to object storage; add it as a direct link resource.",
        ]
        content = "\n".join(p for p in parts if p)
        # For external links the hash is of the URL string, not of any content:
        # identity is the URL, not byte equality.
        sha = hashlib.sha256((item.source_url or item.original).encode("utf-8")).hexdigest()
        return ExtractedDocument(
            source=item,
            title_hint=title_hint,
            content_excerpt=strip_markdown_noise(content, limit=EXCERPT_LIMIT),
            sha256=sha,
            extension=".url",
            size_bytes=0,
            metadata={**metadata, "external_link": True},
        )

    @staticmethod
    def _extract_with_docling(path: Path) -> tuple[str, dict]:
        from docling.document_converter import DocumentConverter

        result = DocumentConverter().convert(str(path))
        markdown = result.document.export_to_markdown()
        name = getattr(result.document, "name", None)
        return markdown, ({"title": name} if name else {})

    def _fallback_extract(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._extract_pdf_fallback(path)
        if ext in {".txt", ".md", ".csv", ".html", ".htm"}:
            return path.read_text(encoding="utf-8", errors="replace")
        return f"No text extractor available for {path.name}. Use filename and metadata only."

    @staticmethod
    def _extract_pdf_fallback(path: Path) -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for i, page in enumerate(reader.pages[:20], start=1):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(f"\n\n## Page {i}\n\n{text}")
        return "".join(parts).strip()
