# SPDX-License-Identifier: MIT
"""Object storage. Uploads never overwrite a published file.

``upload`` asks GCS to create the object only if it does not exist
(``if_generation_match=0``). If it does exist and its MD5 equals the local
file's, the upload is treated as already done (re-runs are idempotent);
otherwise the caller is handed an :class:`ObjectExists` and must pick
another name. Content type is set so PDFs are served as PDFs.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
from collections.abc import Callable
from pathlib import Path

from .errors import IngestError

ProgressCallback = Callable[[int], None]


class ObjectExists(IngestError):
    """The blob name is taken by a different file; choose another name."""


class _ReadCounter:
    """Minimal read-only file proxy that reports bytes read.

    Only ``read`` is proxied because that is all the GCS client uses; every
    other attribute is delegated to the wrapped file object.
    """

    def __init__(self, fileobj, on_read: ProgressCallback):
        self._f = fileobj
        self._on_read = on_read

    def read(self, size: int = -1) -> bytes:
        data = self._f.read(size)
        self._on_read(len(data))
        return data

    def __getattr__(self, name: str):
        return getattr(self._f, name)


def md5_base64(path: Path) -> str:
    """MD5 of a file in the base64 form GCS reports as ``blob.md5_hash``."""
    h = hashlib.md5()  # noqa: S324 – integrity comparison against GCS metadata, not security
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode("ascii")


def content_type_for(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


class GCSUploader:
    def __init__(self, bucket_name: str, public_base_url: str):
        from google.cloud import storage  # lazy: only ingest needs GCS

        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        self.public_base_url = public_base_url.rstrip("/")

    def public_url(self, blob_name: str) -> str:
        return f"{self.public_base_url}/{blob_name.lstrip('/')}"

    def upload(self, source_path: Path, blob_name: str, on_progress: ProgressCallback | None = None) -> str:
        """Create ``blob_name`` from ``source_path``; never replace an existing object.

        Returns the public URL. Raises :class:`ObjectExists` when the name is
        taken by different content. If the same content is already there the
        upload is skipped and the progress callback receives the full size.
        """
        from google.api_core.exceptions import PreconditionFailed

        blob_name = blob_name.lstrip("/")
        blob = self.bucket.blob(blob_name)
        blob.content_type = content_type_for(blob_name)
        total_size = source_path.stat().st_size
        try:
            with source_path.open("rb") as f:
                wrapped = _ReadCounter(f, on_progress) if on_progress else f
                blob.upload_from_file(wrapped, size=total_size, rewind=False, if_generation_match=0)
        except PreconditionFailed:
            existing = self.bucket.get_blob(blob_name)
            if existing is not None and existing.md5_hash == md5_base64(source_path):
                if on_progress:
                    on_progress(total_size)
                return self.public_url(blob_name)
            raise ObjectExists(f"{blob_name} already exists in the bucket with different content.") from None
        return self.public_url(blob_name)
