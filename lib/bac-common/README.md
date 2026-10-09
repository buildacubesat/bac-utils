# bac-common v0.4.1

Build a CubeSat – the shared scaffold every BAC command-line tool is built on. It implements the parts of the BAC Project & Tooling Guide §3 and the BAC Interface Design Guide §10 that are the same for every tool, so a tool contains only its own logic.

Lifted from the CSR Ingest reference implementation (`csr_ingest/ui.py`, `errors.py`, `config.py`, the `main()` boundary in `cli.py`) and generalised.

## 1. What it provides

| Module | Contents |
| :-- | :-- |
| `bac_common.cli` | `make_parser()` with the standard flags (`-v`, `-l`, `--env-file`, `--config`, `--dry-run`, `--init`, hidden `--debug`) and the `Examples:` help block; `run()`, the error boundary that maps errors to exit codes and hides tracebacks unless `--debug`; `help_text()` for the ≤24-line rule |
| `bac_common.ui` | The terminal profile: `opening()` panel, `ok()`/`fail()`/`warn()`/`step()`/`dim()` step lines, `summary()` result block with the dry-run label, `table()`, `fields()`, `spinner()`, `make_progress()`, `error()`, `header()`, `esc()` for untrusted text |
| `bac_common.config` | `default_config_path()`, `load_toml()`, `load_env()`, `pick()` (env over TOML over default), `require_setup()` pointing at `--init`, `write_config()`, `write_env()` (owner-only permissions) |
| `bac_common.sexp` | Span-recording reader for KiCad s-expression files: `parse()`/`parse_file()` give `Node`/`Atom` trees that remember their character spans, `apply_edits()` splices replacements into the original text, `quoted()`/`escape()`/`unescape()` handle KiCad's string escapes, `fmt_number()`, `line_indent()`, `format_version()` |
| `bac_common.cad` | Metadata in exported CAD files: `read_step_header()`/`set_step_header()` fill the `FILE_NAME` entity of a STEP file (model name, author, organisation, authorisation) without touching the data section; `step_product_names()` lists the `PRODUCT` entities |
| `bac_common.gsheets` | Google Sheets through a service account, behind the `gsheets` extra: `SheetsClient.from_service_account()`/`read_range()` returning rows of strings, `credentials_path()` and `credentials_source()` (`BAC_GCP_CREDENTIALS` over the configured path; errors say which of the two set it), `spreadsheet_id()` accepting an id or a URL, `quote_sheet_title()`, `sheet_url()`; API refusals become `ExternalToolError` with the fix as the detail (a 403 names the service account to share the sheet with) |
| `bac_common.errors` | `BacError` with `exit_code` and an optional `detail` line; `ConfigError`, `UsageError` (2), `ExternalToolError`, `UserAbort` (0), `SkipItem` |
| `bac_common.utils` | `sha256_file()`, `short_hash()`, `slugify()`, `safe_filename()`, `is_kebab()` |
| `bac_common.testing` | `invoke()` to run a tool's `main` in-process with captured output, `assert_standard_flags()` for the `-v` and `--help` contract |

## 2. Usage

```python
from bac_common import cli, ui
from bac_common.config import load_env, load_toml, require_setup

TOOL, VERSION = "bac-example", "0.1.0"


def main(argv: list[str], debug: bool) -> int:
    parser = cli.make_parser(
        TOOL,
        VERSION,
        "Copies input files somewhere useful.",
        examples=["bac-example ./in", "bac-example ./in --dry-run"],
    )
    parser.add_argument("source")
    args = parser.parse_args(argv)

    if args.init:  # before any config is loaded: it may not exist yet
        return setup(args.config)

    load_env(args.env_file)
    config = load_toml(TOOL, args.config)
    require_setup(TOOL, config, "paths.target")  # exits with "run bac-example --init" if missing

    ui.opening(TOOL, VERSION, "Copying files.")
    ui.ok(f"Copied {ui.path(args.source)}")
    ui.summary([("Copied", 1), ("Errors", 0)], dry_run=args.dry_run)
    return 0


def entry() -> None:
    cli.run(main)
```

`entry` is the `[project.scripts]` target. Tools with subcommands keep Typer and call `app(args=argv)` inside `main`; `run()` still provides the boundary.

Add the dependency as a workspace source:

```toml
dependencies = ["bac-common>=0.1"]

[tool.uv.sources]
bac-common = { workspace = true }
```

Interactive prompts are not part of the core; install the `prompts` extra (`InquirerPy`) in tools that need guided selection. The Google client libraries are the `gsheets` extra (`google-api-python-client`, `google-auth`); a tool that reads a spreadsheet depends on `bac-common[gsheets]`, every other tool stays without them.

## 3. Rules the helpers enforce

Every message may contain Rich markup, so anything from outside the tool – file names, model output, user input – goes through `ui.esc()` or `ui.path()`. `summary()` right-aligns values and is meant to be called on every exit path, including partial failure. `make_progress()` shows the task name, the bar and exactly one status column. Errors print to stderr as `ERROR message` with an indented next step; the exit codes are 0, 1 and 2 only.

## 4. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.4.1 | 2026-10-08 | `gsheets.credentials_source()` returns the key path together with where it came from, and a missing key file now says whether `BAC_GCP_CREDENTIALS` or the configured setting named it (`configured_as=`, for example `"[credentials] file"`); the variable wins by design, so a stale one in a `.env` above the working directory used to look like a broken config. `ui.py` names `tokens.css` as the source of its colour values. |
| 0.4.0 | 2026-10-07 | `bac_common.gsheets`: the service-account Sheets reader lifted from `bac-update-content-plan` 0.3.0 and generalised, behind the optional `gsheets` extra so no other tool pays for the Google client libraries. Lazy imports, a testable `SheetsClient` wrapper, the key path from `BAC_GCP_CREDENTIALS` or config, ids accepted as URLs, API errors mapped to `ExternalToolError` with the next step (a 403 names the account to share with). |
| 0.3.0 | 2026-10-06 | `bac_common.cad`: the STEP header helper `bac-kicad-generate-artifacts` uses to put the artifact name, author and organisation into the `FILE_NAME` entity in place of the exporter's placeholders; the FreeCAD artifacts tool will add 3MF. Header-only edit: the data section is copied through byte for byte; non-ASCII is written in Part 21's `\X2\…\X0\` form. |
| 0.2.1 | 2026-10-02 | `testing.invoke` pins the Rich consoles to 250 columns and `COLUMNS` to 80 while the tool runs: Rich output is captured unwrapped and untruncated whatever the terminal is, and `--help` is still measured at the width a user sees. Five tests across three tools failed at 80 columns before, because pytest's temporary paths pushed a message past the width. |
| 0.2.0 | 2026-09-07 | `bac_common.sexp`: the span-recording s-expression reader the KiCad tools share, lifted from bac-kicad-tools' `bac_kicad_core.sexpr` and extended with tree helpers (`child`, `value`, `walk`, `find_all`), `parse_file`, `format_version`, overlap-checked `apply_edits`, and string escapes that survive a write-back (`\n`, `\t`, quotes, backslashes). Round-trips the four BAC library fixtures byte for byte. |
| 0.1.1 | 2026-09-04 | `load_env()` searches for `.env` from the current working directory upwards (python-dotenv's default starts at the library's own directory, so an installed tool never found the `.env` next to the user). Returns the path it loaded. `cli.run_typer(app, argv, tool)` runs a Typer app inside the boundary, so usage errors exit 2, `--help` exits 0 and Ctrl-C prints `Interrupted.` and exits 1 instead of Click's `Aborted!` and 130. |
| 0.1.0 | 2026-09-02 | Initial release, lifted from csr_ingest v0.3.1. Compared with the source: values right-aligned in `summary()`, the spinner column removed from the progress bar in favour of one selectable status column, `esc()`/`path()` escaping and a `fields()` helper added, `--debug` stripped from anywhere in argv, Ctrl-C exits 1 instead of 130, `write_env()` writes owner-only files, `require_setup()` and `testing` added. |
