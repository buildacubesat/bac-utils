# bac-issue-print v0.2.0

Build a CubeSat – prints a Codeberg issue or pull request with its whole timeline – comments, reviews with their line comments, pushes, references from other issues, title changes, review requests – as one Markdown document on stdout. Made for handing an issue to a reviewer, a text editor or an LLM session in one go: `bac-issue-print hardware 42 > issue-42.md`. It works against any Forgejo or Gitea instance, Codeberg being the default.

## 1. Install

```sh
uv tool install ./tools/bac-issue-print     # from the bac-utils checkout
bac-issue-print -l
```

The tool works without setup: the built-in keys `docs`, `software`, `hardware` and `structure` map to the BAC repositories under `buildacubesat-project` on Codeberg. `--init` writes that mapping to `~/.config/bac/bac-issue-print.toml` for editing (§4).

## 2. Usage

```
bac-issue-print REPO NUMBER [--comments-only] [--env-file PATH] [--config PATH]
bac-issue-print -l
```

`REPO` is a key from `-l` or a literal `owner/repo`; `NUMBER` is the issue number, with or without `#`. The Markdown goes to stdout, everything else (a spinner while fetching, errors) to stderr, so redirecting stdout gives a clean file.

The timeline is what the issue page shows: every plain comment, every review with its summary and its line comments (a pull request's reviews come from the pull-request API, with their state – approved, changes requested, reviewed), every push with its commits, every reference from another issue or pull request with the referencing comment quoted, title changes, review requests, labels, assignees, milestones, closing and reopening. Lists the server pages are walked through its `Link` header. `--comments-only` prints the plain comments alone, the 0.1 shape, in one request. An entry Forgejo cannot serialise (it sends a literal `null` in the array for those) is skipped and counted on stderr. An issue without a description prints no body instead of the word `null`.

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

## Timeline

### user1 commented – 2026-08-31T01:00:00Z

Comment 1

---

### user2 referenced this from pull request #57 – fix(eps): feed the watchdog from the main loop – 2026-08-31T02:00:00Z

https://codeberg.org/buildacubesat-project/bac-hardware/pulls/57#issuecomment-123

> Fixes #42 – the feed ran from the ISR.

---

### user3 requested changes – 2026-09-01T09:00:00Z

Feed it from the loop, and add the test.

**`src/main.c` line 88**

This still runs from the ISR.
```

One H1 per issue; a pull request shows `State: pull request, open` (or `merged <date>`, or `(draft)`) and its branches; metadata lines that are empty (no labels, no milestone) are omitted; entries are separated by rules and headed `user verb – date`; pushes list their commits as short hashes; a review's line comments follow its summary under the file path and line; `_Nothing happened after the description._` marks an issue without a timeline. With `--comments-only` the section is `## Comments`, the headings are `user – date`, and `_No comments._` marks an empty thread.

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
| 0.2.0 | 2026-10-13 | The timeline instead of the plain comments: reviews with state and line comments (from the pull-request API), pushes, references with the referencing comment quoted, title changes, review requests, labels, assignees, milestones, close and reopen; a pull request's branches and merge state in the header; paged lists walked through the `Link` header; Forgejo's `null` entries skipped and counted. `--comments-only` keeps the 0.1 output. Found on bac-software #154, a pull request whose page showed two reviews and a dozen events where the tool printed one comment. Recorded responses of that pull request are the fixture. 23 tests. |
| 0.1.1 | 2026-10-13 | The tool hung on every issue: 0.1.0 walked comment pages until an empty one, and Forgejo's per-issue comments endpoint ignores `page` and `limit` (its only query parameters are `since` and `before`), so every page came back full until the rate limit ended the run. Now one request for the comments, as the shell script made. Two requests per issue, 18 tests. |
| 0.1.0 | 2026-09-04 | Ported from the `bac-issue` shell script to Python on `bac-common`. Comment pagination, optional token via `.env`/`--env-file`, repository map in `~/.config/bac/bac-issue-print.toml` with `--init` and `-l`, literal `owner/repo` accepted, integer validation of the issue number, HTTP errors reported with status and hint instead of a jq crash after a printed header, empty body prints nothing, one H1 per issue, en dash in comment headings, `-v` and hidden `--debug`, exit 2 for usage errors. 19 tests. |
