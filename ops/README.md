# ops – the business operations suite

Build a CubeSat – the tools that turn hardware into shipped product: what a batch should cost, what was spent and what is in stock, whether each unit is good, and how a paid order becomes a parcel. The suite concept of 2026-07-06 describes four engines over one PostgreSQL store with two run modes, standalone (an engine's own notebook) and orchestrated (one web app with every engine behind a common index). Files are imports and exports, never a second live copy.

| Directory | What it is | Version |
| :-- | :-- | :-- |
| [`../lib/bac-suite-db`](../lib/bac-suite-db/) | The shared layer: `bac.items`, `bac.catalog`, config, SKU scheme, `bac-db` | v0.1.0 |
| [`bac-pricing`](bac-pricing/) | Pricing engine: BOM cost rollup and price derivation, notebook, the `pricing` schema | v1.4.0 |
| [`bac-suite`](bac-suite/) | The orchestrated shell, `bac-suite` | v0.2.0 |

Inventory and spending, quality control and fulfilment follow as engines of their own, each registering its tables and its notebook through the two entry-point groups `bac_suite.engines` and `bac_suite.apps`.

## 1. Getting started

```sh
uv run bac-db --init              # backend, data directory, DSN (writes ~/.config/bac/bac-suite.toml and <data_dir>/.env)
cp ops/bac-pricing/examples/* ~/bac/ops-data/
uv run bac-db migrate             # schemas and tables
uv run bac-db import pricing      # the data files into the database
uv run bac-pricing                # the pricing notebook, standalone
uv run bac-suite                  # the orchestrated shell on http://127.0.0.1:2718
```

Without Postgres, answer `files` to the backend question: the engines then read and write the data directory directly. The example data under `ops/bac-pricing/examples/` is Build a CubeSat's own set, published deliberately; replace it with yours.

Two network calls happen at run time: the notebooks load their fonts from Google Fonts, and the pricing notebook's "Sync FX" button fetches exchange rates from frankfurter.dev. Nothing else leaves the machine. Marimo has no authentication: `--host 0.0.0.0` exposes an editable notebook to the network, and both launchers say so.

## 2. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.10.0 | 2026-10-07 | Written with the suite's arrival in bac-utils (root 0.10.0): the shared layer, the pricing engine and the shell. |
