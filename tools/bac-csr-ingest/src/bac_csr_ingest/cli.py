# SPDX-License-Identifier: MIT
"""Command-line interface: ``ingest``, ``sync-blocks``, ``check-blocks``, ``init``.

Typer app plus the argv normalisation that lets bare inputs route to
``ingest``. The error boundary is :func:`bac_common.cli.run`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import typer
from InquirerPy import inquirer

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import write_config, write_env

from . import __version__
from .config import CONFIG_TEMPLATE, ENV_TEMPLATE, TOOL, Config, load_config, resolve_config_path
from .errors import BacError, ResolverError, SkipItem, SyncError, UserAbort
from .extract import DocumentExtractor
from .llm import LLMClassifier
from .models import ExtractedDocument
from .plan import (
    PlannedItem,
    already_indexed,
    commit_subject_for_group,
    group_planned_by_section,
    hashed_blob_name,
    is_external_link,
    make_plan_item,
    print_plan,
    record_for,
    rel,
    validate_placements,
)
from .repo import RepoContext, git_commit
from .resolver import InputResolver
from .resources import ResourceIndex
from .review import confirm, review
from .storage import GCSUploader, ObjectExists
from .sync import SyncReport, indexed_urls_by_block, prune, sync

COMMANDS = {"ingest", "sync-blocks", "check-blocks", "init"}
GLOBAL_OPTIONS_WITH_VALUE = {"--env-file", "--config"}
GLOBAL_TERMINAL_FLAGS = {"-v", "--version", "-l", "--list", "-h", "--help"}

app = typer.Typer(
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    help=(
        "Build a CubeSat – ingest documents and links into the CubeSat Resources site "
        "and keep data/resources.yml in sync with its CSR-RESOURCES blocks.\n\n"
        "\b\n"
        "Examples:\n"
        "  bac-csr-ingest check-blocks\n"
        "  bac-csr-ingest sync-blocks --dry-run\n"
        "  bac-csr-ingest ./incoming report.pdf https://example.com/doc.pdf\n"
        "  bac-csr-ingest links.lst --hint 'manufacturer is Endurosat'"
    ),
)


@dataclass(slots=True)
class Global:
    env_file: str | None
    config: str | None


# ---------------------------------------------------------------------------
# Entry point and global options
# ---------------------------------------------------------------------------


def main() -> None:
    """``[project.scripts]`` target."""
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    # Docling's OCR backend logs at INFO by default; keep the step log clean.
    logging.getLogger("RapidOCR").setLevel(logging.WARNING)
    logging.getLogger("rapidocr").setLevel(logging.WARNING)
    app(args=normalize_argv(argv), prog_name=TOOL)
    return 0


def normalize_argv(argv: list[str]) -> list[str]:
    """Route bare inputs to ``ingest``.

    Typer requires global options before the command, so the scan skips
    ``--env-file X`` / ``--config X`` and looks at the first other token: a
    command or a terminal flag (``-v``, ``-l``, ``--help``) is left alone;
    anything else – a path, a URL, or an ``ingest`` option such as
    ``--hint`` – gets ``ingest`` inserted in front of it.
    """
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in GLOBAL_OPTIONS_WITH_VALUE:
            i += 2
            continue
        if token.startswith(("--env-file=", "--config=")):
            i += 1
            continue
        break
    if i >= len(argv) or argv[i] in COMMANDS or argv[i] in GLOBAL_TERMINAL_FLAGS:
        return list(argv)
    return [*argv[:i], "ingest", *argv[i:]]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(bac_cli.version_string(TOOL, __version__))
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "-v", "--version", callback=_version_callback, is_eager=True, help="Print version and exit."
    ),
    list_blocks: bool = typer.Option(False, "-l", "--list", help="List block ids on the site and exit."),
    env_file: str | None = typer.Option(
        None, "--env-file", metavar="PATH", help="Load this .env instead of the default."
    ),
    config: str | None = typer.Option(
        None, "--config", metavar="PATH", help=f"TOML config (default: ~/.config/bac/{TOOL}.toml)."
    ),
) -> None:
    ctx.obj = Global(env_file=env_file, config=config)
    if list_blocks:
        cfg = load_config(env_file, config)
        for b in RepoContext(cfg.repo_root, cfg.docs_path).scan().blocks:
            typer.echo(b.block_id)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def _load(ctx: typer.Context) -> tuple[Config, RepoContext, ResourceIndex]:
    g: Global = ctx.obj
    cfg = load_config(g.env_file, g.config)
    repo = RepoContext(cfg.repo_root, cfg.docs_path)
    index = ResourceIndex(cfg.resource_index_path)
    return cfg, repo, index


# ---------------------------------------------------------------------------
# check-blocks / sync-blocks
# ---------------------------------------------------------------------------


@app.command("check-blocks")
def check_blocks(ctx: typer.Context) -> None:
    """Report differences and problems between resources.yml and the site's blocks. Never writes."""
    cfg, repo, index = _load(ctx)
    ui.opening(TOOL, __version__, "Checking resources.yml against CSR-RESOURCES blocks.")
    report = sync(repo.scan(), index, apply=False)
    _print_report(report, verbose=True)
    _print_report_summary(report, index, dry_run=False, wrote=False)
    if not report.clean:
        raise typer.Exit(1)


@app.command("sync-blocks")
def sync_blocks(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change; write nothing."),
    prune_orphans: bool = typer.Option(False, "--prune", help="Remove index records whose URL is in no block."),
    yes: bool = typer.Option(False, "--yes", help="Do not ask before pruning."),
    no_commit: bool = typer.Option(False, "--no-commit", help="Do not create a Git commit."),
) -> None:
    """Backfill resources.yml from the CSR-RESOURCES blocks on the site. Never edits markdown."""
    cfg, repo, index = _load(ctx)
    ui.opening(TOOL, __version__, "Backfilling resources.yml from CSR-RESOURCES blocks. Markdown is not modified.")
    report = sync(repo.scan(), index, apply=not dry_run)
    _print_report(report, verbose=False)

    pruned = 0
    if prune_orphans and report.orphans:
        if dry_run:
            ui.step(f"Would prune {len(report.orphans)} orphan record(s).")
        else:
            if not yes and not confirm(f"Remove {len(report.orphans)} orphan record(s) from the index?"):
                raise UserAbort()
            pruned = prune(index, report.orphans)

    wrote = False
    if not dry_run and (report.pending or pruned):
        index.write()
        wrote = True
        ui.ok(f"Wrote {ui.path(rel(cfg.resource_index_path, cfg.repo_root))}")
        if not no_commit:
            parts = [f"{report.pending} change(s)"] + ([f"{pruned} pruned"] if pruned else [])
            subject = f"Resources: sync index with site blocks ({', '.join(parts)})"
            if git_commit(cfg.repo_root, subject, [rel(cfg.resource_index_path, cfg.repo_root)]):
                ui.ok(f"Committed: {ui.esc(subject)}")

    _print_report_summary(report, index, dry_run=dry_run, wrote=wrote, pruned=pruned)
    remaining = report.problems - pruned
    if remaining:
        ui.warn(f"{remaining} problem(s) need attention. Run check-blocks for details.")


def _print_report(report: SyncReport, verbose: bool) -> None:
    for p in report.marker_problems:
        ui.fail(f"{ui.path(f'{p.file}:{p.line_no}')} {ui.esc(p.message)}")
    for bid, blocks in report.duplicate_block_ids:
        where = ", ".join(ui.path(f"{b.file}:{b.start_line}") for b in blocks)
        ui.fail(f"Block id '{ui.esc(bid)}' defined in: {where}")
    for block, line in report.unparsed:
        ui.fail(f"{ui.path(f'{block.file}:{line.line_no}')} unparsed line in '{ui.esc(block.block_id)}'")
        ui.dim(f"    {ui.esc(_clip(line.raw.strip()))}")
    for url, block in report.duplicate_urls:
        ui.fail(f"{ui.path(f'{block.file}:{block.start_line}')} URL listed twice in '{ui.esc(block.block_id)}'")
        ui.dim(f"    {ui.esc(_clip(url))}")
    for url, blocks, detail in report.inconsistent:
        ids = ", ".join(ui.esc(b.block_id) for b in blocks)
        ui.fail(f"URL cross-listed in {ids} but entries differ: {ui.esc(detail)}")
        ui.dim(f"    {ui.esc(_clip(url))}")
    for block, reason in report.invalid_block_ids:
        ui.warn(f"{ui.path(f'{block.file}:{block.start_line}')} block id '{ui.esc(block.block_id)}': {ui.esc(reason)}")
    for o in report.orphans:
        ui.warn(f"Orphan in index: {ui.esc(o.record.title)} – {ui.esc(o.reason)}")
        ui.dim(f"    {ui.esc(_clip(o.record.url))}")

    if verbose or len(report.added) <= 20:
        for c in report.added:
            ui.step(f"[dim]add[/]     {ui.esc(c.where)}: {ui.esc(_clip(c.detail, 60))}")
    else:
        ui.step(f"[dim]add[/]     {len(report.added)} entries (run check-blocks to list them)")
    for c in report.moved:
        ui.step(f"[dim]move[/]    {ui.esc(c.detail)}")
        ui.dim(f"    {ui.esc(_clip(c.url))}")
    for c in report.updated:
        ui.step(f"[dim]update[/]  {ui.esc(c.where)} ({ui.esc(c.detail)})")
        ui.dim(f"    {ui.esc(_clip(c.url))}")


def _clip(value: str, limit: int = 72) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _print_report_summary(
    report: SyncReport, index: ResourceIndex, dry_run: bool, wrote: bool, pruned: int = 0
) -> None:
    rows: list[tuple[str, int | str]] = [
        ("Blocks", report.blocks_scanned),
        ("Entries", report.entries_scanned),
        ("Indexed", len(index)),
        ("Added", len(report.added)),
        ("Moved", len(report.moved)),
        ("Updated", len(report.updated)),
        ("Orphans", len(report.orphans)),
        ("Problems", report.problems),
    ]
    if pruned:
        rows.append(("Pruned", pruned))
    if wrote:
        rows.append(("Index", "written"))
    ui.summary(rows, dry_run=dry_run)


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Counters:
    planned: int = 0
    uploaded: int = 0
    linked: int = 0
    skipped: int = 0
    commits: int = 0

    def rows(self) -> list[tuple[str, int | str]]:
        return [
            ("Planned", self.planned),
            ("Uploaded", self.uploaded),
            ("Linked", self.linked),
            ("Skipped", self.skipped),
            ("Commits", self.commits),
        ]


@app.command("ingest")
def ingest(
    ctx: typer.Context,
    inputs: list[str] = typer.Argument(..., help="Files, URLs, folders, or list files (.lst / '# csr-list' header)."),
    hint: str | None = typer.Option(
        None, "--hint", help="Free-text guidance for the classifier, applied to every input."
    ),
    auto_apply: bool = typer.Option(
        False, "--auto-apply", help="Accept existing-block placements; still ask for new blocks/pages."
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Accept everything, including new blocks/pages. Implies --auto-apply."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; no uploads, writes, or commits."),
    no_commit: bool = typer.Option(False, "--no-commit", help="Do not create Git commits."),
) -> None:
    """Classify, upload, index and place new resources."""
    cfg, repo, index = _load(ctx)
    if yes:
        auto_apply = True
    ui.opening(TOOL, __version__, "Ingesting resources into the CubeSat Resources site.")

    # Pre-flight: the index must agree with the site before anything is written,
    # otherwise render could overwrite manual entries or resurrect removed ones.
    scan = repo.scan()
    report = sync(scan, index, apply=False)
    if not report.clean:
        raise SyncError(
            f"Index is not in sync with the site ({report.pending} pending change(s), {report.problems} problem(s)).",
            f"Run `{TOOL} sync-blocks` (and check-blocks) first.",
        )
    ui.dim(f"Index in sync: {report.blocks_scanned} blocks, {len(index)} resources.")

    counters = Counters()
    with TemporaryDirectory(prefix="bac-csr-ingest-") as tmp:
        resolver = InputResolver(tmp, notify=lambda m: ui.warn(ui.esc(m)))
        with ui.spinner("Resolving inputs…"):
            items = resolver.resolve_many(inputs, hint=hint)
        if not items:
            raise ResolverError("No supported input documents found.")
        ui.step(f"Found {len(items)} input document(s).")
        if not dry_run and any(i.kind != "external_url" for i in items):
            cfg.require_upload()

        extractor = DocumentExtractor()
        docs: list[ExtractedDocument] = []
        with ui.make_progress("count") as progress:
            task = progress.add_task("Extracting", total=len(items))
            for item in items:
                progress.update(task, description=f"Extracting {ui.esc(Path(item.original).name[:40])}")
                docs.append(extractor.extract(item))
                progress.advance(task)

        blocks = repo.block_targets(scan)
        sections = repo.candidate_sections()
        classifier = LLMClassifier(cfg.llm_provider, cfg.llm_model)

        planned: list[PlannedItem] = []
        used_blob_names: set[str] = set()
        for doc in docs:
            try:
                existing = already_indexed(index, doc)
                if existing:
                    ui.warn(f"Already indexed in '{ui.esc(existing)}': {ui.esc(doc.source.original)}")
                    raise SkipItem()
                with ui.spinner(f"Classifying {ui.esc(Path(doc.source.original).name[:40])}…"):
                    decision = classifier.classify(doc, blocks, sections, notify=lambda m: ui.warn(ui.esc(m)))
                decision = review(decision, blocks, auto_apply=auto_apply, yes=yes)
                planned.append(make_plan_item(cfg, doc, decision, used_blob_names))
            except SkipItem:
                counters.skipped += 1
                ui.dim(f"Skipped: {ui.esc(doc.source.original)}")

        counters.planned = len(planned)
        if not planned:
            ui.step("Nothing to do – all items were skipped.")
            ui.summary(counters.rows(), dry_run=dry_run)
            return

        # Every placement is checked against the repository before the plan
        # is shown, so what the user confirms is what will happen.
        known = {b.block_id: b.file for b in scan.blocks}
        validate_placements(planned, repo, known)
        print_plan(planned)

        if dry_run:
            counters.linked = sum(1 for i in planned if is_external_link(i))
            counters.uploaded = counters.planned - counters.linked
            ui.summary(counters.rows(), dry_run=True)
            return

        if not auto_apply and not confirm("Apply this ingest plan?"):
            raise UserAbort()

        try:
            _apply_plan(cfg, repo, index, planned, counters, no_commit=no_commit)
        finally:
            ui.summary(counters.rows(), dry_run=False)


def _apply_plan(
    cfg: Config,
    repo: RepoContext,
    index: ResourceIndex,
    planned: list[PlannedItem],
    counters: Counters,
    *,
    no_commit: bool,
) -> None:
    """Uploads first, then markdown, then index, render and commits.

    Ordered so that a failure leaves the least to clean up: a failed upload
    changes nothing locally; a failure after uploads leaves objects in the
    bucket that a re-run reuses (same content, same name).
    """
    # Phase 1: upload. Names are never reused for different content.
    uploader: GCSUploader | None = None
    with ui.make_progress("percent") as progress:
        for item in planned:
            if is_external_link(item):
                counters.linked += 1
                ui.ok(f"Linked:   {ui.path(item.public_url)}")
                continue
            src = item.document.source.staged_path
            assert src is not None
            if uploader is None:
                uploader = GCSUploader(cfg.bucket_name, cfg.public_base_url)  # type: ignore[arg-type]
            task = progress.add_task(f"Uploading {ui.esc(src.name[:40])}", total=src.stat().st_size)
            try:
                item.public_url = uploader.upload(
                    src, item.blob_name, on_progress=lambda n, t=task: progress.advance(t, n)
                )
            except ObjectExists:
                item.blob_name = hashed_blob_name(item.blob_name, item.document.sha256)
                progress.reset(task)
                item.public_url = uploader.upload(
                    src, item.blob_name, on_progress=lambda n, t=task: progress.advance(t, n)
                )
            progress.remove_task(task)
            counters.uploaded += 1
            ui.ok(f"Uploaded: {ui.path(item.public_url)}")

    # Phase 2: create any new blocks/pages. Paths were validated in validate_placements.
    created: set[str] = set()
    for item in planned:
        d = item.decision
        if d.placement_type == "new_block_requested" and item.block_id not in created:
            assert item.markdown_file is not None
            repo.ensure_block_after_heading(
                item.markdown_file, d.suggested_heading or "Resources", item.block_id, d.suggested_parent_heading
            )
            created.add(item.block_id)
        elif d.placement_type == "new_page_requested" and item.block_id not in created:
            assert item.markdown_file is not None
            repo.create_page_with_block(
                item.markdown_file, d.suggested_nav_title or d.suggested_heading or d.title, item.block_id
            )
            created.add(item.block_id)
            ui.warn(f"New page {ui.path(item.markdown_file)} was created but not added to mkdocs.yml nav.")

    # Phase 3: index, render only the blocks touched, commit per section.
    for item in planned:
        index.upsert(record_for(item))
    index.write()
    touched_blocks = {item.block_id for item in planned}
    repo.render_blocks(index.rendered_lines_by_block(), indexed_urls_by_block(index), only=touched_blocks)
    index_rel = rel(cfg.resource_index_path, cfg.repo_root)

    if not no_commit:
        for section, group in group_planned_by_section(planned).items():
            paths = {index_rel, *(i.markdown_file for i in group if i.markdown_file)}
            subject = commit_subject_for_group(section, group)
            if git_commit(cfg.repo_root, subject, sorted(paths)):
                counters.commits += 1
                ui.ok(f"Committed: {ui.esc(subject)}")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command("init")
def init(ctx: typer.Context) -> None:
    """First-time setup: write the TOML config and a .env with the secret paths."""
    g: Global = ctx.obj
    config_path = Path(g.config).expanduser() if g.config else resolve_config_path(None)
    env_path = Path(g.env_file).expanduser() if g.env_file else Path(".env")
    ui.opening(TOOL, __version__, "First-time setup.")

    repo_root = (
        inquirer.text(message="Path to the CubeSat-Resources repository:", default=str(Path.cwd())).execute().strip()
    )
    bucket = inquirer.text(message="GCS bucket name:").execute().strip()
    public_base_url = (
        inquirer.text(message="Public base URL:", default=f"https://storage.googleapis.com/{bucket}" if bucket else "")
        .execute()
        .strip()
    )
    credentials = inquirer.text(message="Path to service-account JSON key:").execute().strip()
    provider = inquirer.select(message="LLM provider:", choices=["openai", "claude"], default="openai").execute()
    model = (
        inquirer.text(message="LLM model:", default="gpt-4.1-mini" if provider == "openai" else "").execute().strip()
    )
    api_key = (
        inquirer.secret(message=f"{'OPENAI' if provider == 'openai' else 'ANTHROPIC'}_API_KEY (blank to skip):")
        .execute()
        .strip()
    )

    if config_path.exists() and not inquirer.confirm(message=f"Overwrite {config_path}?", default=False).execute():
        raise UserAbort()
    write_config(
        config_path,
        CONFIG_TEMPLATE.format(
            repo_root=repo_root, bucket=bucket, public_base_url=public_base_url, llm_provider=provider, llm_model=model
        ),
        overwrite=True,
    )
    ui.ok(f"Wrote {ui.path(config_path)}")

    # Only keys with values are written uncommented: an empty KEY= line would
    # blank a key already exported in the shell when the .env is loaded.
    key_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    other = "ANTHROPIC_API_KEY" if provider == "openai" else "OPENAI_API_KEY"
    api_key_lines = (f"{key_name}={api_key}\n" if api_key else f"# {key_name}=\n") + f"# {other}=\n"
    if write_env(env_path, ENV_TEMPLATE.format(credentials=credentials, api_key_lines=api_key_lines)):
        ui.ok(f"Wrote {ui.path(env_path)} (owner-only permissions)")
    else:
        ui.warn(f"{ui.path(env_path)} exists; not overwritten.")
        ui.dim(f"Make sure it sets CSR_GOOGLE_APPLICATION_CREDENTIALS and {key_name}.")

    try:
        load_config(str(env_path) if env_path.exists() else None, str(config_path))
        ui.ok("Configuration validates.")
    except BacError as exc:
        ui.warn(ui.esc(str(exc)))


if __name__ == "__main__":
    main()
