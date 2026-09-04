# bac-convention-check v0.2.0

Build a CubeSat – scans a repository for drift from the BAC conventions and prints a report that can go straight into a review or an LLM session. It is the linter this monorepo runs in CI on itself.

Rules are data, not code: two sets ship with the tool. `guide` encodes the BAC Project & Tooling Guide v0.11 and the BAC Interface Design Guide v0.1 (typography, naming, licensing, packaging, versioning, README structure, URLs, terminology). `firmware` carries the review heuristics of the flight software and hardware repositories (stale part references, addressing, CAN configuration, buffer patterns); those encode decisions of bac-software and bac-hardware, not of the guides, and are theirs to own. Any other set is a TOML file you point the tool at.

## 1. Install

```sh
uv tool install ./tools/bac-convention-check     # from the bac-utils checkout
bac-convention-check ~/repos/some-repo
```

No `--init`: the tool has no persistent settings of its own. A repository may carry a `bac-convention-check.toml` at its root (§4).

## 2. Usage

```
bac-convention-check [ROOT] [--rules SET]... [--only IDS] [--severity all|blocking]
                     [--max-hits N] [--format terminal|report|tsv] [--config PATH] [-l] [-v]
```

`ROOT` defaults to the current directory. Files come from `git ls-files` when the root is a git checkout (so `.gitignore` is honoured and untracked files are included), otherwise from a directory walk that skips build, cache and dependency directories. Binary files (a NUL byte in the first 8 KiB) and files over 5 MiB are never scanned.

The output format is `terminal` when stdout is a terminal and `report` when it is piped, so `bac-convention-check > scan.txt` gives the plain, delimited form without asking:

```
=== Build a CubeSat – bac-convention-check v0.2.0
run_utc: 2026-09-02T14:05:00Z
root: /home/user/repos/bac-utils
files: 64 (git ls-files)
rules: guide
...
--- CHECK A1 | blocking | Em dash present (only the en dash is permitted)
hits: 2
docs/intro.md:14:The board — a 1U frame — ships bare.
note: output truncated at 1 hits (1 more)
--- END A1
...
=== SUMMARY
ID   SEVERITY  HITS   TITLE
A1   blocking  2      Em dash present (only the en dash is permitted)
...
verdict: 2 blocking finding(s)
=== END
```

`hits:` is always the full count; `--max-hits` (default 40, 0 for unlimited) only limits how many lines are printed. `tsv` gives one row per finding: id, severity, path, line, text. Exit codes: `0` clean, `1` blocking findings or a rule that failed to run, `2` bad arguments.

## 3. Rules

Run `bac-convention-check -l` for the selected sets. The `guide` set:

| Id | Severity | Rule |
| :-- | :-- | :-- |
| `A1` | blocking | Em dash present (only the en dash is permitted) |
| `A2` | blocking | Lowercase x used for multiplication or dimensions |
| `A3` | blocking | Decorative emoji (semantic glyphs ✓ ✗ ! → · are exempt) |
| `A4` | blocking | Curly apostrophe or single quote |
| `A5` | advisory | Curly double quotes |
| `A6` | advisory | ß in German text (use ss) |
| `A7` | advisory | Comma thousands separator on a CHF or metric value |
| `B1` | blocking | Mixed-case BAC (always fully capitalised in prose; lowercase bac in code) |
| `B2` | blocking | buildacubesat used as a display name |
| `B3` | blocking | Mixed-case bac in a file or directory name |
| `F1` | blocking | Retired guide or token names |
| `H1` | blocking | Possible hardcoded secret |
| `H2` | advisory | YAML outside framework-required paths |
| `L1` | blocking | Source file without an SPDX MIT header in its first lines |
| `L2` | blocking | pyproject.toml without an MIT license field |
| `L3` | advisory | pyproject.toml license not in the guide's table form |
| `P1` | blocking | pyproject.toml requires-python below 3.11 or missing |
| `P2` | advisory | pyproject.toml build backend is not hatchling |
| `P3` | advisory | Dependency with an upper bound, exact pin, or no minimum |
| `P4` | blocking | Project name without the bac- prefix |
| `P5` | advisory | Script entry point not shaped bac-toolname = bac_toolname.cli:main |
| `V1` | blocking | CLI module without a --version flag |
| `V2` | advisory | Version number encoded in a file name |
| `R1` | blocking | README without a version history section |
| `R2` | advisory | README that never names Build a CubeSat |
| `U1` | advisory | GitHub URL for a BAC repository that is hosted on Codeberg |
| `S1` | advisory | Master/slave terminology |

The `firmware` set (`--rules guide --rules firmware`):

| Id | Severity | Rule |
| :-- | :-- | :-- |
| `B9` | blocking | Mixed-case Roci |
| `C1` | advisory | BAC_ vs ROCI_ prefix inventory (unsettled decision) |
| `D1` | advisory | Hardcoded 31 or 0x1F near addressing (broadcast is netmask-derived) |
| `D2` | blocking | aliveNodes narrower than U64 |
| `E1` | blocking | ADS1113 reference (the part is ADS1115) |
| `E2` | blocking | ADS1113 symbol or devicetree node |
| `E3` | advisory | Wrong CAN controller family (carrier part is MCP251863) |
| `E4` | blocking | CAN FD enabled (small nodes are bxCAN, CAN 2.0B only) |
| `E5` | blocking | Stale 'no CAN hardware' or 'CAN planned' status |
| `E6` | blocking | STM32F4 variant other than F405 |
| `E7` | advisory | BNO055 reference outside history and driver context (the part is BNO086) |
| `E8` | advisory | More than one CAN transceiver family named |
| `E9` | advisory | Part named in docs but absent from devicetree, Kconfig and sources |
| `G1` | advisory | GPIO return value ignored |
| `G2` | advisory | csp_send call sites (check for use-after-free) |
| `G3` | advisory | Static global buffers (check for races) |

### 3.1 Writing a rule set

```toml
[[rules]]
id = "X1"                       # unique across all loaded sets
severity = "blocking"           # or advisory
title = "What went wrong, in one line"
kind = "regex"                  # regex | require | path | builtin
pattern = "—"                   # Python regex
include = ["*.md", "**/docs/**"]  # globs; omitted = every text file
exclude = ["CHANGELOG.md"]
drop = "0x[0-9a-f]"             # lines matching this are discarded
keep = "addr|node"              # only lines matching this survive
ignore_case = true
note = "How to fix it."         # shown under the findings
```

`regex` reports every matching line. `require` reports every selected file that lacks the pattern (within the first `head_lines` lines when set). `path` matches the repo-relative path. `builtin` names an analysis in `builtins.py` for checks that need structure, such as parsing `pyproject.toml`. A pattern without `/` matches file names; one with `/` matches the whole relative path, `**` included.

## 4. Adapting for your own project

Put a `bac-convention-check.toml` at the repository root (or pass `--config PATH`):

```toml
# bac-convention-check.toml
# Build a CubeSat – bac-convention-check configuration for this repository
rules = ["guide", "rules/house.toml"]   # bundled names or paths relative to this file
max_hits = 40

[exclude]                       # paths a rule must skip; "*" applies to every rule
"*" = ["vendor/**"]
A1 = ["src/parser.py"]          # the parser tolerates em dashes on purpose
```

A single line opts out with a marker in a comment: `# convention-check: allow A1` (several ids comma-separated, or `all`). A project with its own conventions replaces `guide` with its own set; the bundled sets are plain TOML to copy from.

## 5. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.2.0 | 2026-09-02 | Ported from shell to Python on `bac-common`. Rules moved into TOML sets; the 16 firmware heuristics split into `firmware`, the guide conventions into `guide` with new rules for curly quotes, ß, thousands separators, mixed-case file names, SPDX headers, pyproject fields (license, requires-python, backend, pins, name, scripts), `--version` presence, versions in file names, README version history and first reference, GitHub URLs for Codeberg-hosted repositories, and master/slave terminology. One deterministic file walk (git-aware, binary sniff) replaces the rg/grep split; HTML, CSS, JSON and extension-less files are scanned. Counts are taken before truncation; unknown `--only` ids and a missing option value are usage errors; the amber check matches whole words; E9 orphan parts are findings, not notes. Added `terminal` output, project config with per-rule excludes, inline allow markers, custom rule sets. 22 tests. |
| 0.1.0 | – | Shell script with 23 checks, `report` and `tsv` output. |
