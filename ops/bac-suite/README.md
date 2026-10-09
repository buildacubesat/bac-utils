# bac-suite v0.2.1

Build a CubeSat – the orchestrated run mode of the business operations suite: one web app with an index page and every installed engine's notebook behind its own route, all reading the same store. The shell holds no logic of its own; an engine registers its notebook under the `bac_suite.apps` entry-point group and appears on the index as soon as it is installed next to the shell. Today that is pricing at `/pricing`.

## 1. Install

```sh
uv tool install ./ops/bac-suite        # from the bac-utils checkout; pulls bac-pricing and bac-suite-db
bac-suite --init                       # once: backend, data directory, DSN (the suite's shared setup)
bac-suite                              # http://127.0.0.1:2718
```

Inside the checkout, `uv run bac-suite`. `-l` lists the registered notebooks with their routes; `--dry-run` prints what would be served and stops. The shell binds to localhost; `--host 0.0.0.0` prints a warning, because marimo has no authentication and anyone who reaches the port can edit and save. Ctrl-C stops the server.

## 2. How a notebook joins

```toml
[project.entry-points."bac_suite.apps"]
pricing = "bac_pricing:APP"
```

where `APP` is `{"label": "Pricing", "route": "/pricing", "notebook": <path>}`. The notebook resolves the backend itself through the suite config and `BAC_DB_DSN`, which the shell exports into its own environment before marimo starts. The index page links every engine and takes its colours, fonts and motion from `/tokens.css`, which the shell serves from a copy of the reference gallery's shared stylesheet (`src/bac_suite/static/tokens.css`; a test keeps it identical to `tools/bac-reference-gallery/css/tokens.css`, so after a change there, copy the file over): it follows the system's light or dark setting, shows the yellow accent and a visible focus ring, and respects reduced motion.

## 3. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.2.1 | 2026-10-09 | The index page links `/tokens.css`, a copy of the reference gallery's shared stylesheet served by the shell, instead of carrying its own colour values (its muted grey and focus blue differed from the tokens); the fonts come with the stylesheet. 14 tests. |
| 0.2.0 | 2026-10-07 | Joins bac-utils as `ops/bac-suite` on `bac-common` and `bac-suite-db`: engines found through the `bac_suite.apps` entry-point group instead of a hard-coded table, the suite's shared `--init`, `--config`, `--env-file`, `--dry-run`, `-l`, `-v`, hidden `--debug`, the `--host` warning, the index page on the BAC tokens with escaped labels; the ASGI app is testable without uvicorn. 11 tests. |
| 0.1.0 | 2026-07-06 | `bac_suite.py` in bac-pricing 1.3.0: marimo's ASGI app builder with pricing as the first entry, an index page. |
