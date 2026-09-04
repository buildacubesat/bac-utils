# bac-csr-ingest v0.4.0

Build a CubeSat – ingestion and index maintenance for the [CubeSat Resources](https://cubesat-resources.space) site. It classifies documents and links with an LLM, uploads files to Google Cloud Storage, indexes them in `data/resources.yml`, writes them into the site's `CSR-RESOURCES` blocks, and commits. It is also the reference implementation for the BAC CLI conventions; `bac-common` was lifted from it.

## 1. The model

The site is edited by hand as well as by this tool, so the two sources of truth are split:

- **Markdown blocks** are authoritative for *which* resource is in *which* block, and for the visible title, type badge and description.
- **`data/resources.yml`** is authoritative for everything else: publisher, author, year, resource type, tags, hash, provenance.

The tool never writes a block it has not first read. `sync-blocks` pulls the markdown into the index; `ingest` refuses to run until the index agrees with the site; and the renderer refuses to touch any block containing a line it cannot parse or a URL the index does not know.

A block is the region between a marker pair:

```markdown
<!-- CSR-RESOURCES:START solar-cell-datasheets -->
- **[Azur 3G30C](https://…/3g30c.pdf)** `PDF` – Triple-junction cell datasheet
<!-- CSR-RESOURCES:END solar-cell-datasheets -->
```

Entries may be written by hand in looser forms (`- [Title](url) - desc`, no bold, no badge, description on the next line, URLs with parentheses); sync reads them, and the next render normalises them to the canonical line above. A URL may be cross-listed in several blocks as long as it reads identically in each; the index records all of them in `block_ids`. Prose outside blocks is never touched.

### 1.1 What the classifier is allowed to do

The classifier reads untrusted documents, so its output is treated as untrusted too. Titles, descriptions, headings and tags are stripped of HTML and control characters before they can reach markdown; block ids must be kebab-case; paths must be relative `.md` files inside `docs/`, and a new block's parent page must already exist. A decision that fails these rules is fed back to the model for one retry, then rejected. Uploads never replace an object that already exists in the bucket: the same content is reused, different content gets a hash-suffixed name.

## 2. Install

```sh
uv tool install ./tools/bac-csr-ingest              # from the bac-utils checkout
uv tool install './tools/bac-csr-ingest[extract]'   # with Docling for better PDF extraction (large)
bac-csr-ingest init
```

`init` asks for the repository path, bucket, public URL, service-account key, LLM provider and model, and API key. It writes `~/.config/bac/bac-csr-ingest.toml` and a `.env` (owner-only permissions) in the current directory. Non-secret settings live in the TOML file; secrets in `.env`. Any `CSR_*` environment variable overrides the TOML value, so an `.env`-only setup also works. A config left by the previous `csr-ingest` name at `~/.config/bac/csr-ingest.toml` is still read.

Without the `extract` extra the tool falls back to pypdf for PDFs and plain text for text files.

## 3. Commands

```
bac-csr-ingest check-blocks                 # report drift and problems, exit 1 if any; never writes
bac-csr-ingest sync-blocks [--dry-run] [--prune [--yes]] [--no-commit]
                                            # backfill the index from the site's blocks; never edits markdown
bac-csr-ingest ingest <inputs…> [--hint …] [--auto-apply | --yes] [--dry-run] [--no-commit]
bac-csr-ingest <inputs…>                    # same as `ingest`; ingest options may come first too
bac-csr-ingest --list                       # block ids on the site
bac-csr-ingest --version
```

Global options `--env-file PATH` and `--config PATH` go before the command. `--debug` may go anywhere and shows tracebacks.

### 3.1 Inputs

Files, folders, URLs, and list files. A list file is recognised by a `.lst` extension, or by a first line of `# csr-list` in a `.txt`, `.md` or extension-less file; one input per line, `#` comments allowed. A per-line hint follows `::`:

```
# csr-list
https://example.com/doc.pdf :: treat as datasheet, manufacturer is Endurosat
./incoming/report.pdf
```

`--hint "…"` applies to every input that has no line hint. List files found inside a folder are skipped, not expanded; name them explicitly.

### 3.2 Typical workflow

1. `bac-csr-ingest check-blocks` – see what the site has that the index does not.
2. `bac-csr-ingest sync-blocks` – backfill. Fix any reported unparsed lines or duplicate URLs by hand and re-run until `check-blocks` is clean.
3. `bac-csr-ingest ingest …` – add new resources. The pre-flight sync check runs automatically.

`sync-blocks` reports index records whose URL no longer appears in any block as orphans and leaves them alone; `--prune` removes them after a confirmation (`--yes` skips it). Orphans block `ingest` because rendering would otherwise re-insert a link someone deliberately deleted.

### 3.3 What an ingest run does, in order

Resolve inputs, extract text, classify, review, then validate every placement against the repository and show the plan. After confirmation: upload files (nothing local has changed if this fails), create new blocks or pages, write the index, render only the touched blocks, and commit once per section. The result summary is printed on every exit, including failures.

## 4. Exit codes

`0` success (including a user abort), `1` error or `check-blocks` found problems, `2` bad arguments.

## 5. Adapting for your own project

The tool assumes an MkDocs site with `CSR-RESOURCES` marker pairs and a YAML index at `data/resources.yml` (the YAML file is an inherited data format, kept as-is). Paths, bucket, public URL and the `CSR_*` prefix are configuration; the marker name and the entry format live in `blocks.py`. The classifier prompt in `llm.py` names CubeSat Resources and its category conventions and is the one place to edit for a different site.

## 6. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.4.0 | 2026-09-02 | Renamed from `csr-ingest` to `bac-csr-ingest` and moved into the bac-utils monorepo on `bac-common`. Classifier output is sanitised and shape-checked (HTML and control characters stripped, kebab-case block ids, paths confined to `docs/`, parent pages must exist), also on interactive edits. Uploads use a generation guard: identical content is reused, different content gets a hash-suffixed name; content type is set. Ingest applies uploads before markdown edits and prints its summary on failure. `--prune` asks for confirmation (`--yes`). Options such as `--hint` may precede the inputs. `# csr-list` header honoured in `.txt`, `.md` and extension-less files. `init` writes `.env` with owner-only permissions and asks for the API key. Docling is an optional `extract` extra. `cli.py` split into `plan.py` and `review.py`; dead helpers removed; Ctrl-C exits 1. |
| 0.3.1 | 2026-08-27 | Cross-listing via `block_ids`; parser accepts URLs with parentheses and a description on the following line; report layout for 80 columns. |
| 0.3.0 | 2026-08-27 | `sync-blocks`, `check-blocks`, guarded `render_blocks`, ingest pre-flight, Typer CLI with the standard flags, TOML config, BAC terminal profile, list files with hints. |
