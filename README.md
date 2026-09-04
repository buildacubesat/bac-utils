# bac-utils

Build a CubeSat – the utilities that keep the project running: KiCad release and library tooling, Blender video editing helpers, media conversion, content and resource pipelines, repository checks, and the business operations suite. Every tool follows the [BAC Project & Tooling Guide](https://buildacubesat.space) and the BAC Interface Design Guide, so they look and behave alike: the same flags, the same terminal output, the same config locations.

The repository holds the generally usable state of each tool. Anything specific to one project – vendor prices, sheet IDs, repository paths, plugin locations – lives in your own config and data directories, created by each tool's `--init`. What ships here is the tool, sample data under `examples/`, and an `.env.example` where secrets are involved. See §5 to adapt a tool for your own project.

## 1. Tools

| Tool | Domain | What it does | Status | Version |
| :-- | :-- | :-- | :-- | :-- |
| `bac-common` | library | Shared CLI scaffold: standard flags, TOML config, `.env` loading, `--init` helpers, the BAC terminal profile, error boundary | available | v0.1.1 |
| `bac-convention-check` | repo | Lints a tree against the BAC guides (typography, naming, licensing, packaging, flags); runs in this repo's CI | available | v0.2.0 |
| `bac-csr-ingest` | resources | Ingests documents and links into the CubeSat Resources site: extraction, LLM classification, review, upload, index, commit | available | v0.4.0 |
| `bac-issue-print` | repo | Prints a Codeberg issue with all comments as Markdown | available | v0.1.0 |
| `bac-kicad-generate-artifacts` | KiCad | Produces the release bundle for a KiCad project: render, pinout, schematic PDF, BOM, iBOM, Gerbers, drills, STEP, QR marker, ZIP | planned | – |
| `bac-kicad-hlabels` | KiCad | Emits hierarchical-label blocks for a list of net names, ready to paste into a schematic | available | v0.1.0 |
| `bac-kicad-symlint` | KiCad | Lints and fixes text sizes and footprint references in KiCad symbol and footprint libraries, preserving file formatting | planned | – |
| `bac-markdown-to-youtube` | content | Converts Markdown to YouTube description markup | available | v0.2.0 |
| `bac-media-convert` | media | Batch conversions: square WebP for the shop, constant-frame-rate MP4 from variable-rate WebM | available | v0.1.0 |
| `bac-reference-gallery` | design | Design-reference pages for the BAC guides plus a PNG/PDF renderer; home of the shared `tokens.css` | planned | – |
| `bac-shop-product-cropper` | media | Interactive crop of product photos with size-targeted WebP export | planned | – |
| `bac-update-content-plan` | content | Renders the content plan from a Google Sheet into the docs repository and commits it | planned | – |
| `bac-vse-tools` | Blender | One extension with three sub-panels: bulk import, sequential proxies, separate meta strips preserving trim | planned | – |
| `bac-pricing`, `bac-suite`, `bac-suite-db` | ops | Business operations suite on Marimo and PostgreSQL: pricing engine and notebook, orchestrated shell, shared database schema and `bac-db` CLI | planned | – |

Related, maintained elsewhere: [`bac-page`](https://github.com/buildacubesat/bac.page/tree/main/cli), the CLI for the bac.page URL shortener, lives with the GitHub Pages repository it writes to.

## 2. Install

Each tool is its own `uv` project and installs independently:

```sh
uv tool install ./tools/bac-issue-print
bac-issue-print --init
```

The Blender extension is installed from a zip built in `blender/bac-vse-tools`. The ops suite is described in `ops/README.md`.

To work on the repository itself:

```sh
uv sync --all-packages
uv run pytest
uv run ruff check .
```

## 3. Layout

```
lib/       shared libraries (bac-common, bac-suite-db)
tools/     one directory per CLI tool, installable with uv tool install
ops/       business operations suite (Marimo notebooks + PostgreSQL)
blender/   Blender extensions
```

Every tool directory has the same shape: `pyproject.toml`, `src/bac_<name>/cli.py`, `README.md` with a version history, `tests/`, and where the tool consumes data, `examples/`.

## 4. Conventions

Every CLI tool supports `-v/--version`, `--dry-run`, hidden `--debug`, `--env-file PATH`, `--config PATH` and `--init`, and `-l/--list` where it operates on a named set. Config lives at `~/.config/bac/<tool>.toml`; secrets in a `.env` file loaded with python-dotenv. Exit codes are 0 for success, 1 for a runtime error, 2 for bad arguments. Errors go to stderr; tracebacks appear only with `--debug`. Terminal output uses the BAC Interface Design Guide's terminal profile through `bac_common.ui`.

Software in this repository is licensed MIT; documentation CC BY-SA 4.0. Software versions follow SemVer and display with a `v` prefix.

## 5. Adapting for your own project

Run `<tool> --init`. It asks for the paths, identifiers and endpoints the tool needs, writes `~/.config/bac/<tool>.toml`, and where secrets are involved, a `.env` next to your working directory with empty values to fill in. Tools that consume data files take a data directory from that config; the copies under each tool's `examples/` show the expected shape and can be copied as a starting point. Nothing in the repository needs editing to point a tool at your own project.

## 6. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.4.0 | 2026-09-04 | Four small tools on the scaffold: `bac-markdown-to-youtube` v0.2.0 (rewritten conversion), `bac-issue-print` v0.1.0 (ported from shell, pagination, token), `bac-kicad-hlabels` v0.1.0 (flags, `--gap-on-blank`), `bac-media-convert` v0.1.0 (`webp-square`, `cfr`; the two shell loops retired). `bac-common` v0.1.1: `.env` is searched from the working directory, `run_typer` puts Typer tools inside the error boundary. |
| 0.3.0 | 2026-09-02 | `bac-convention-check` v0.2.0 ported to Python with TOML rule sets; runs on the repository in CI. |
| 0.2.0 | 2026-09-02 | `bac-csr-ingest` v0.4.0: first tool on `bac-common`; classifier trust boundary, upload guard, phase order. Root pytest runs in importlib mode so tools may share test module names. |
| 0.1.0 | 2026-09-02 | Repository skeleton: uv workspace, CI, `bac-common` v0.1.0 lifted from the CSR Ingest reference implementation. Tools follow in the homogenization plan's order. |
