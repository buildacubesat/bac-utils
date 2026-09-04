# bac-csr-ingest – To-Do

Updated 2026-09-02 (v0.4.0). Completed items are kept in the "Done" section for one release, then removed.

## Blocking / next

- [ ] **Run `check-blocks` and `sync-blocks` against the real site** and fix whatever the parser reports (unparsed lines, duplicate URLs, marker problems). Ingest stays paused until `check-blocks` is clean.
- [ ] **Correct the product-specific block id** `lightfoundry-space-grade-30-percent-gaas-14466-datasheet` → `solar-cell-datasheets` in the markdown; `check-blocks` will keep warning about it until then.
- [ ] **`sync-blocks --enrich`** – run the classifier for metadata only (publisher, author, year, resource_type, tags) on records with `added_by: sync`. Placement is fixed; the prompt needs a metadata-only mode.

## Correctness

- [ ] **`new_page_requested` must update `mkdocs.yml` nav** – pages created by `create_page_with_block` are never added to the nav. Currently a warning is printed; inject the entry or print the exact snippet.
- [ ] **Naming heuristics in `sync.check_block_id`** are conservative (`\d{3,}`, `percent`, singular `-datasheet`). Revisit once a `taxonomy` file exists.
- [ ] **`render_blocks` re-sorts entries alphabetically**, discarding hand-chosen order. Decide whether order is authored (then preserve it) or canonical (then say so in the README).

## Reliability

- [ ] **Resume / checkpoint on batch failure** – uploads are now idempotent (same content, same name is reused), so a re-run after a failure is safe; a JSON checkpoint would let it skip classification for items already decided.

## Performance

- [ ] **Concurrent URL fetching** – `resolve_many` is serial; add a bounded `ThreadPoolExecutor`.
- [ ] **Extraction caching** – cache Docling/OCR output keyed by SHA256 at `~/.cache/bac/bac-csr-ingest/extracted/<sha>.json`.

## New features

- [ ] **`list` / `status` subcommand** – query the index by tag, section, type.
- [ ] **`remove` subcommand** – remove a resource from the index, render its block, optionally delete the GCS blob, commit.
- [ ] **S3 and local-copy storage backends.**
- [ ] **Smarter repo / website metadata extraction** – GitHub, GitLab, Codeberg, arXiv structured metadata before the LLM call. Note: add a token env var later for rate limits.
- [ ] **Duplicate detection beyond URL/SHA256** – normalised titles, URL canonicalisation beyond host/scheme, fuzzy filenames.
- [ ] **Taxonomy stabilisation** – `data/taxonomy.toml` with canonical section names, preferred tags, valid placement patterns; fed to the classifier and to `check-blocks`.
- [ ] **Automatic related-tag suggestions** – co-occurrence first, embeddings later.

## Tests

- [ ] Unit tests for `llm.py` (retry loop with a fake provider) and `extract.py`.
- [ ] Integration test for the new-block and new-page phases end to end.
- [ ] Cap on downloaded size in `resolver._resolve_url` (currently unbounded).

## Done in v0.4.0

- [x] Renamed to `bac-csr-ingest`; moved into the bac-utils monorepo on `bac-common` (terminal profile, errors, config, error boundary). The old config path is still read.
- [x] Classifier output sanitised and shape-checked in `ResourceDecision`, on construction and on assignment.
- [x] Block ids validated on the ingest path; markdown paths confined to `docs/`; parent pages must exist; all checked before the plan is shown.
- [x] GCS uploads never overwrite (`if_generation_match=0`); identical content reused, different content hash-suffixed; content type set.
- [x] Ingest order: uploads → markdown → index → render → commit; summary printed on failure.
- [x] `--prune` confirms (or `--yes`); `--prune --dry-run` reports what it would remove; `remaining` count fixed.
- [x] `normalize_argv` accepts ingest options before the inputs.
- [x] `# csr-list` header honoured in `.txt`, `.md` and extension-less files; list files inside folders skipped with a notice.
- [x] `init` writes `.env` with owner-only permissions, asks for the API key, never writes an empty `KEY=` line.
- [x] Docling moved to the optional `extract` extra.
- [x] `cli.py` split into `plan.py` and `review.py`; `ui.py`, `suggest_block_id`, `normalize_block_id`, duplicate `HEADING_RE` removed; git errors reported as tool errors; ruff clean.
- [x] Tests: 60 (was 24) – models, plan, path guard, resolver, storage guard, boundary behaviour, hostile input end to end.
