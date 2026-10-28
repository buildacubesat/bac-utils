# bac-page v0.5.0

Build a CubeSat – the command line of the [bac.page](https://bac.page) URL shortener. Every short link is a folder in the [Pages repository](https://github.com/buildacubesat/bac-page) with an `index.html` redirect in it; the tool writes the folder, commits and pushes, and GitHub Pages serves the link within about half a minute. Part of [bac-utils](https://github.com/buildacubesat/bac-utils) (`tools/bac-page/`) since 0.5.0; it lived in the Pages repository's `cli/` folder before.

## 1. Install

```sh
uv tool install ./tools/bac-page     # from the bac-utils checkout
bac-page --init
```

`--init` asks for the path to your local clone of the Pages repository (`~/bac/bac-page` offered) and writes it to `~/.config/bac/bac-page.toml`. A `BAC_PAGE_REPO` variable – from the shell, a `.env` in the directory you run the tool from (or above it), or `--env-file PATH` – overrides the file. The legacy `~/.config/bac-page/.env` is read once more in 0.5, with a note, unless `--env-file` is given; 0.6 stops reading it.

## 2. Usage

```
bac-page <url> [slug] [--qr]    create a redirect; a random 8-character slug when omitted
bac-page list                   every redirect, sorted by slug
bac-page edit                   change a slug or destination, or make a QR code
bac-page init                   set the repository path (same as --init)
```

Slugs are 1–24 characters: letters, digits and hyphens. `add` is the explicit form of the create command (`bac-page add <url> [slug]`). A create commits the folder, pulls with rebase and pushes in one go; `edit` shows the change and asks before it pushes. A slug that is renamed stops resolving under its old name – QR codes and shared links to it break – and the tool says so; whether a rename should leave a redirect behind is an open question for a later version.

QR options of `add`: `--format svg|png|webp` (default svg), `--invert` (white on black), `--alpha` (transparent background), `--ec L|M|Q|H` (default M), `--size PX` (default 1000), `--output DIR` (default `~`). Files are named `bac-page-<slug>.<format>`; `edit` asks for the same options interactively.

Standard flags: `-v/--version`, `-l/--list`, `--init`, `--config PATH`, `--env-file PATH`, `--dry-run` (shows what would be written and pushed), and a hidden `--debug` that prints tracebacks. `list` prints a table in a terminal and tab-separated `short-url<TAB>destination` lines when piped or with `--plain`.

Exit codes: `0` done, also when `edit` is cancelled; `1` a runtime error – the repository is not configured or missing, a slug is taken, git refused; `2` bad arguments, a malformed slug or target among them.

## 3. Adapting for your own project

The domain is `DOMAIN` in `redirects.py`, the redirect page `redirect_html()` there; the repository is whatever `--init` is pointed at – any GitHub Pages (or similar static) repository where a folder with an `index.html` becomes a path. Folders named in `SKIP_DIRS` are left out of `list` and `edit`.

## 4. Tests

```sh
uv run pytest tools/bac-page
```

The tests run the commands against a throwaway git repository with a bare remote, so `add` and `edit` push for real; the prompts of `edit` are replaced by scripted answers; QR codes are written in the three formats and read back.

## 5. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.5.0 | 2026-10-28 | Moved into bac-utils as `tools/bac-page` on `bac-common`: the standard parser and error boundary (`ERROR …` on stderr, exit codes 0/1/2 – a malformed slug or target exits 2 now, 0.4 exited 1; no command prints the help to stderr; option names are not abbreviated any more; a `--config` that names a missing file is an error instead of "not configured"), the opening panel and summary, `ui` output, the shared config loader (`--init` writes through it, overwrites on re-run and offers `~/bac/bac-page`), `.env` found from the working directory upwards. A subcommand's `--help` reaches the subcommand (0.4 printed the root help). `git add` and `git mv` take `--`, so a slug that starts with a hyphen works; a missing `git` is reported as such; `--output` for a QR code is created when it does not exist. The legacy `~/.config/bac-page/.env` is read with a deprecation note and goes in 0.6. The QR writer uses Pillow alone for transparent PNG and WebP (numpy dropped; the files are byte-identical). Tests: 36 on a throwaway repository with a bare remote. Commands, slugs, redirect files, QR options and git behaviour otherwise unchanged. |
| 0.4.2 | 2026-10-21 | `--init` warns when `BAC_PAGE_REPO` overrides the path it just saved; a missing repo path set by `BAC_PAGE_REPO` names the variable instead of pointing to `--init`. |
| 0.4.1 | 2026-10-21 | Repository renamed from `bac.page` to `bac-page`: prompts, help text and the default `--init` path use the new name. |
| 0.4.0 | 2026-08-28 | `list` (slug and destination columns) and `edit` become subcommands (`--list`/`--edit` flag forms kept as `-l/--list`; `--edit` removed). `list` sorts alphabetically by slug and renders a Rich table. Aligned with BAC Project & Tooling Guide v0.11 and Interface Design Guide v0.1: Rich output and spinner during git operations, `v`-prefixed version, `--config`/`--env-file`/`--dry-run`/`--debug` flags, TOML config at `~/.config/bac/bac-page.toml` (legacy `~/.config/bac-page/.env` still read), InquirerPy prompts with confirmation before pushes, `git mv` for renames, target URL validation, MIT license and pinned minimum dependency versions in `pyproject.toml`. Fixed slug error message (limit is 24, not 12). |
| 0.3.5 | – | `--list`, `--edit`, `--version` flags; QR generation with format, inversion, transparency, error correction, and size options; python-dotenv config. |
