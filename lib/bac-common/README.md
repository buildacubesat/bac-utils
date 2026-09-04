# bac-common v0.1.1

Build a CubeSat – the shared scaffold every BAC command-line tool is built on. It implements the parts of the BAC Project & Tooling Guide §3 and the BAC Interface Design Guide §10 that are the same for every tool, so a tool contains only its own logic.

Lifted from the CSR Ingest reference implementation (`csr_ingest/ui.py`, `errors.py`, `config.py`, the `main()` boundary in `cli.py`) and generalised.

## 1. What it provides

| Module | Contents |
| :-- | :-- |
| `bac_common.cli` | `make_parser()` with the standard flags (`-v`, `-l`, `--env-file`, `--config`, `--dry-run`, `--init`, hidden `--debug`) and the `Examples:` help block; `run()`, the error boundary that maps errors to exit codes and hides tracebacks unless `--debug`; `help_text()` for the ≤24-line rule |
| `bac_common.ui` | The terminal profile: `opening()` panel, `ok()`/`fail()`/`warn()`/`step()`/`dim()` step lines, `summary()` result block with the dry-run label, `table()`, `fields()`, `spinner()`, `make_progress()`, `error()`, `header()`, `esc()` for untrusted text |
| `bac_common.config` | `default_config_path()`, `load_toml()`, `load_env()`, `pick()` (env over TOML over default), `require_setup()` pointing at `--init`, `write_config()`, `write_env()` (owner-only permissions) |
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

Interactive prompts are not part of the core; install the `prompts` extra (`InquirerPy`) in tools that need guided selection.

## 3. Rules the helpers enforce

Every message may contain Rich markup, so anything from outside the tool – file names, model output, user input – goes through `ui.esc()` or `ui.path()`. `summary()` right-aligns values and is meant to be called on every exit path, including partial failure. `make_progress()` shows the task name, the bar and exactly one status column. Errors print to stderr as `ERROR message` with an indented next step; the exit codes are 0, 1 and 2 only.

## 4. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.1 | 2026-09-04 | `load_env()` searches for `.env` from the current working directory upwards (python-dotenv's default starts at the library's own directory, so an installed tool never found the `.env` next to the user). Returns the path it loaded. `cli.run_typer(app, argv, tool)` runs a Typer app inside the boundary, so usage errors exit 2, `--help` exits 0 and Ctrl-C prints `Interrupted.` and exits 1 instead of Click's `Aborted!` and 130. |
| 0.1.0 | 2026-09-02 | Initial release, lifted from csr_ingest v0.3.1. Compared with the source: values right-aligned in `summary()`, the spinner column removed from the progress bar in favour of one selectable status column, `esc()`/`path()` escaping and a `fields()` helper added, `--debug` stripped from anywhere in argv, Ctrl-C exits 1 instead of 130, `write_env()` writes owner-only files, `require_setup()` and `testing` added. |
