# SPDX-License-Identifier: MIT
"""Configuration.

Two layers, following the BAC Project & Tooling Guide §3.6–3.7:

* ``~/.config/bac/bac-csr-ingest.toml`` – non-secret settings a human edits by
  hand (paths, bucket, public URL, LLM provider/model, GCS prefix).
* ``.env`` – secrets and machine-specific paths (service-account key, API keys).

Environment variables ``CSR_*`` override the TOML values, so an ``.env``-only
setup keeps working unchanged. The pre-0.4 config path
``~/.config/bac/csr-ingest.toml`` is still read when the new one is absent.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from bac_common.config import default_config_path, load_env, load_toml, pick

from .errors import ConfigError

TOOL = "bac-csr-ingest"
LEGACY_TOOL = "csr-ingest"

CONFIG_TEMPLATE = """# bac-csr-ingest.toml
# Build a CubeSat – bac-csr-ingest configuration

[source]
repo_root = "{repo_root}"
docs_dir = "docs"
resource_index = "data/resources.yml"

[upload]
bucket = "{bucket}"
public_base_url = "{public_base_url}"
gcs_prefix = "resources"

[llm]
provider = "{llm_provider}"
model = "{llm_model}"
"""

ENV_TEMPLATE = """# Build a CubeSat – bac-csr-ingest secrets
# Never commit this file.

CSR_GOOGLE_APPLICATION_CREDENTIALS={credentials}
{api_key_lines}"""


class Config(BaseModel):
    repo_root: Path
    docs_dir: str = "docs"
    resource_index: str = "data/resources.yml"
    bucket_name: str | None = None
    google_credentials: Path | None = None
    public_base_url: str | None = None
    gcs_prefix: str = "resources"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1-mini"

    @property
    def docs_path(self) -> Path:
        return self.repo_root / self.docs_dir

    @property
    def resource_index_path(self) -> Path:
        return self.repo_root / self.resource_index

    def require_upload(self) -> None:
        """Validate the settings only ingest needs; sync/check never upload."""
        missing = [
            name
            for name, value in (
                ("bucket / CSR_BUCKET_NAME", self.bucket_name),
                ("public_base_url / CSR_PUBLIC_BASE_URL", self.public_base_url),
                ("CSR_GOOGLE_APPLICATION_CREDENTIALS", self.google_credentials),
            )
            if not value
        ]
        if missing:
            raise ConfigError(f"Upload settings missing: {', '.join(missing)}.", f"Run `{TOOL} init`.")
        assert self.google_credentials is not None
        if not self.google_credentials.exists():
            raise ConfigError(f"Service account key file does not exist: {self.google_credentials}")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(self.google_credentials)


def resolve_config_path(config_path: str | None) -> Path:
    """Explicit path, else the tool's default, else the pre-0.4 ``csr-ingest.toml``."""
    if config_path:
        return Path(config_path).expanduser()
    default = default_config_path(TOOL)
    legacy = default_config_path(LEGACY_TOOL)
    if not default.exists() and legacy.exists():
        return legacy
    return default


def load_config(env_file: str | None = None, config_path: str | None = None) -> Config:
    load_env(env_file)
    path = resolve_config_path(config_path)
    toml = load_toml(TOOL, path) if path.exists() else {}
    source = toml.get("source", {})
    upload = toml.get("upload", {})
    llm = toml.get("llm", {})

    repo_root = pick("CSR_REPO_ROOT", source, "repo_root")
    if not repo_root:
        raise ConfigError("No repository configured.", f"Set CSR_REPO_ROOT or run `{TOOL} init`.")

    credentials = pick("CSR_GOOGLE_APPLICATION_CREDENTIALS", upload, "google_credentials")
    cfg = Config(
        repo_root=Path(str(repo_root)).expanduser().resolve(),
        docs_dir=str(pick("CSR_DOCS_DIR", source, "docs_dir", "docs")),
        resource_index=str(pick("CSR_RESOURCE_INDEX", source, "resource_index", "data/resources.yml")),
        bucket_name=_opt(pick("CSR_BUCKET_NAME", upload, "bucket")),
        google_credentials=Path(str(credentials)).expanduser().resolve() if credentials else None,
        public_base_url=(str(pick("CSR_PUBLIC_BASE_URL", upload, "public_base_url") or "")).rstrip("/") or None,
        gcs_prefix=str(pick("CSR_GCS_PREFIX", upload, "gcs_prefix", "resources")),
        llm_provider=str(pick("CSR_LLM_PROVIDER", llm, "provider", "openai")),
        llm_model=str(pick("CSR_LLM_MODEL", llm, "model", "gpt-4.1-mini")),
    )

    if not cfg.repo_root.exists():
        raise ConfigError(f"Repository root does not exist: {cfg.repo_root}")
    if not cfg.docs_path.exists():
        raise ConfigError(f"Docs directory does not exist: {cfg.docs_path}")
    return cfg


def _opt(value: object) -> str | None:
    return str(value) if value else None
