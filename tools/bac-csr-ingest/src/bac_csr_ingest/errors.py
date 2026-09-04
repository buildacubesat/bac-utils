# SPDX-License-Identifier: MIT
"""Error taxonomy. Every expected failure is a :class:`BacError` from bac-common.

The boundary in :func:`bac_common.cli.run` turns these into ``ERROR …`` on
stderr and the right exit code; tracebacks appear only with ``--debug``.
"""

from __future__ import annotations

from bac_common.errors import BacError, ConfigError, ExternalToolError, SkipItem, UserAbort

__all__ = [
    "BacError",
    "ConfigError",
    "ExternalToolError",
    "IngestError",
    "ResolverError",
    "ClassificationError",
    "LLMProviderError",
    "LLMResponseError",
    "PlacementError",
    "SyncError",
    "UserAbort",
    "SkipItem",
]


class IngestError(BacError):
    """Base class for this tool's pipeline errors."""


class ResolverError(IngestError):
    """Inputs cannot be resolved (missing file, unreadable list file, empty batch)."""


class ClassificationError(IngestError):
    """Base for all LLM-classifier failures."""


class LLMProviderError(ClassificationError):
    """The configured LLM provider is unsupported or unusable (unknown name, missing key)."""


class LLMResponseError(ClassificationError):
    """The LLM returned an unparseable or schema-invalid response after all retries."""


class PlacementError(IngestError):
    """A placement decision is invalid (unknown block id, bad path, bad type)."""


class SyncError(IngestError):
    """The index and the site's resource blocks are not in a state that permits writing.

    Raised when a render would overwrite content the index does not know
    about, or when ingest is attempted while ``sync-blocks`` has pending work.
    """
