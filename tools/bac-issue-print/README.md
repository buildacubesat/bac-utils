# bac-issue-print v0.1.0

Build a CubeSat – prints a Codeberg issue with all of its comments as one Markdown document on stdout. Made for handing an issue to a reviewer, a text editor or an LLM session in one go: `bac-issue-print hardware 42 > issue-42.md`. It works against any Forgejo or Gitea instance, Codeberg being the default.

## 1. Install

```sh
uv tool install ./tools/bac-issue-print     # from the bac-utils checkout
bac-issue-print -l
```

The tool works without setup: the built-in keys `docs`, `software`, `hardware` and `structure` map to the BAC repositories under `buildacubesat-project` on Codeberg. `--init` writes that mapping to `~/.config/bac/bac-issue-print.toml` for editing (§4).

## 2. Usage

```
bac-issue-print REPO NUMBER [--env-file PATH] [--config PATH]
bac-issue-print -l
```

`REPO` is a key from `-l` or a literal `owner/repo`; `NUMBER` is the issue number, with or without `#`. The Markdown goes to stdout, everything else (a spinner while fetching, errors) to stderr, so redirecting stdout gives a clean file.

Comments are fetched page by page (the API caps a page at 50), so long threads arrive complete; the shell script this replaces stopped after the first page. An issue without a description prints no body instead of the word `null`.

A Codeberg access token in `CODEBERG_TOKEN` – from a `.env` in the working directory, `--env-file PATH`, or the environment – makes private repositories readable and raises the rate limit. `.env.example` shows the variable. Public repositories need no token.

Exit codes: `0` printed, `1` the API refused or could not be reached (the message names the HTTP status and a next step), `2` bad arguments (unknown key, non-numeric issue number).

## 3. Output shape

```markdown
# Watchdog resets the MCU (buildacubesat-project/bac-hardware #42)

- Author: mnu
- State: open
- Created: 2026-08-30T10:11:12Z
- Labels: bug, eps
- Milestone: R2
- URL: https://codeberg.org/buildacubesat-project/bac-hardware/issues/42

The board resets every 4 s under load.

## Comments

### user1 – 2026-08-31T01:00:00Z

Comment 1

---

### user2 – 2026-08-31T02:00:00Z

Comment 2
```

One H1 per issue; metadata lines that are empty (no labels, no milestone) are omitted; comments are separated by rules; `_No comments._` marks an empty thread.

## 4. Adapting for your own project

`bac-issue-print --init` writes:

```toml
# bac-issue-print.toml
# Build a CubeSat – bac-issue-print configuration. Keys under [repos] are what you
# type on the command line; values are repository names under `owner`.
host = "https://codeberg.org"
owner = "buildacubesat-project"

[repos]
docs = "bac-docs"
software = "bac-software"
hardware = "bac-hardware"
structure = "bac-structure"
```

Point `host` at your own Forgejo or Gitea instance, `owner` at your organisation, and list the repositories you reach for most often under `[repos]`. Anything not listed is still reachable as `owner/repo`.

## 5. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-09-04 | Ported from the `bac-issue` shell script to Python on `bac-common`. Comment pagination, optional token via `.env`/`--env-file`, repository map in `~/.config/bac/bac-issue-print.toml` with `--init` and `-l`, literal `owner/repo` accepted, integer validation of the issue number, HTTP errors reported with status and hint instead of a jq crash after a printed header, empty body prints nothing, one H1 per issue, en dash in comment headings, `-v` and hidden `--debug`, exit 2 for usage errors. 19 tests. |
