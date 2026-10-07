# bac-suite-db v0.1.0

Build a CubeSat – the PostgreSQL layer the business operations suite shares: the `bac.items` and `bac.catalog` tables every engine keys on, the bootstrap configuration (backend, data directory, connection string), the SKU scheme as a parser, an in-memory stand-in connection for tests, and the `bac-db` command that creates the schema and moves an engine's data between its files and the database.

The suite concept (2026-07-06) puts Postgres at the centre: one store, several engines – pricing today, inventory, quality control and fulfilment to come – and files only as imports and exports. This library is what the engines build on; `bac-pricing` is the first.

## 1. Install

```sh
uv tool install ./lib/bac-suite-db --with ./ops/bac-pricing    # from the bac-utils checkout
bac-db --init
bac-db migrate
bac-db import pricing ~/bac/ops-data
```

`--with` installs the engines whose data `bac-db` should know about; without one it manages the shared tables only. Inside the checkout `uv run bac-db …` sees every workspace engine. Postgres itself is a native install (`apt install postgresql`, Homebrew, the Windows installer) or a managed instance; the suite needs a database and a role, nothing else.

## 2. Configuration

`bac-db --init` asks three things and writes two files:

| File | Holds |
| :-- | :-- |
| `~/.config/bac/bac-suite.toml` | `[storage] backend = "postgres"` or `"files"`, and `data_dir`, the directory with the CSV/TOML data files (import source, export target, and the working set in files mode) |
| `<data_dir>/.env` (mode 600) | `BAC_DB_DSN=postgresql://user:password@host:5432/database` – the connection string lives here because it carries a password, never in the TOML |

Every suite tool resolves the same two files, so `bac-pricing --init` and `bac-suite --init` run this setup too. `--config PATH` and `--env-file PATH` override the locations for one run; `BAC_SUITE_CONFIG` and `BAC_DATA_DIR` in the environment do the same; the launchers hand `BAC_SUITE_CONFIG` and `BAC_DB_DSN` to their marimo subprocess that way. The `.env` is searched the usual way (`--env-file`, then the nearest `.env` above the working directory) and, while `BAC_DB_DSN` is still unset, in the data directory – so a notebook started from anywhere finds it, and another tool's `.env` nearer by does not hide it. The DSN is never accepted on the command line, where it would land in the shell history, and is shown as host and database only.

`backend = "files"` runs the engines from the data directory's files without a database – the way to start before Postgres exists. The shipped sample data is `ops/bac-pricing/examples/`.

## 3. The `bac-db` command

```
bac-db [--config PATH] [--env-file PATH] [-l] [--init] COMMAND
  migrate                  create the shared schema and every installed engine's tables (safe to re-run)
  status                   row counts per table and each engine's own status line
  import ENGINE [DIR]      replace the engine's tables from its data files (asks first; -y, --dry-run)
  export ENGINE DIR        write the engine's tables as its data files
```

`import` validates every file, the catalog included, before it opens a connection (bad data never reaches the database), then names the tables it is about to replace with their row counts and asks `[y/N]`; `--dry-run` reports the same without touching anything. Shared rows are upserted, never deleted: an item row is replaced column by column from the importing engine's file (the file is the register's source), a catalog row keeps its stored value in every column the file leaves empty, so a shipping weight entered elsewhere survives a pricing re-import. `export` refuses a folder that already holds the engine's files unless `--force` is given. `-l` lists the installed engines.

Exit codes: 0 done (a declined confirmation included), 1 a runtime error (no database, bad data), 2 bad arguments.

## 4. For engine authors

An engine registers an `Engine` record under the `bac_suite.engines` entry-point group and gets `migrate`, `import`, `export` and `status` for free:

```toml
[project.entry-points."bac_suite.engines"]
pricing = "bac_pricing.store:ENGINE"
```

| Module | Contents |
| :-- | :-- |
| `bac_suite_db.schema` | `SHARED_DDL`, `Engine(name, ddl, tables, files, plan, import_files, export_files, status)`, `discover_engines()`, `migrate(conn, engines)`, `table_counts()` |
| `bac_suite_db.items` | `upsert_items()`, `load_items()`, `upsert_catalog()`, `load_catalog()` – string-valued rows in the CSV shape; SKUs validated on the way in |
| `bac_suite_db.config` | `load_settings()`, `require_setup()`, `require_dsn()`, the templates `--init` writes |
| `bac_suite_db.db` | `connect(dsn)` – psycopg, with a failure message that names host and database only |
| `bac_suite_db.dsn` | `redact()`, `describe()` |
| `bac_suite_db.sku` | `SKU_PATTERN`, `parse_sku()`, `validate_sku()`, `is_sku()`, `SkuError` |
| `bac_suite_db.testing` | `FakeConn` – an in-memory connection that understands the statements the suite issues, so engine tests run without Postgres |

The shared tables are `bac.items` (one row per BOM node: id, SKU, name, type, category, vendor, customs fields, sellable, domain) and `bac.catalog` (one row per sellable SKU: shipping dimensions, HS code, legal country of origin, customs description, declared value, ECCN, origin story, GS1 barcode, image and license references). Their columns are the suite concept's §4.3, unchanged from bac-pricing 1.3.0.

## 5. SKUs

The scheme is the Project & Tooling Guide's §2.9: `bac-<cat>-<sub>-<name>-<versionstring>[-<variant>]`, every field lowercase, hyphens between fields and inside a name, the hardware version string `v<N>r<N>[.<N>]` as the anchor and an optional store variant after it (`-b` for B-stock, `-hdr`, `-eu`). A name may carry dots for legibility (`1.5u`). Shopify accepts dots in a SKU; some fulfilment partners' warehouse systems allow only letters, digits, `/`, `\`, `-` and `_`, so a third-party logistics onboarding may one day ask for `1-5u`. A SKU outside the scheme is an error, never a warning, wherever the suite writes one: `bac-db import` refuses the files and the shared-layer upserts raise; the pricing notebook shows the problem in its Checks callout.

## 6. Tests

```sh
uv run pytest lib/bac-suite-db
BAC_TEST_DSN=postgresql://postgres@localhost/bac_test uv run pytest ops/bac-pricing/tests/test_live.py
```

The unit tests run on `FakeConn`. The live tests (in the pricing engine) run only with `BAC_TEST_DSN` set and only against a database whose name contains `test`: they drop and recreate the `bac` and `pricing` schemas. The configured `BAC_DB_DSN` is never used by a test.

## 7. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-10-07 | Lifted from bac-pricing 1.3.0's `bac_store.py` as the suite's shared layer: the `bac` schema and the engine registry (entry points), `bac-db` as a Typer tool on `bac-common` with `--init`, `migrate`, `status`, `import` (validated first, confirmed, `--dry-run` names the deletes) and `export`; the DSN moves to `.env` as `BAC_DB_DSN` and is shown redacted everywhere; the catalog seed moves out of the code into the data (`bac-catalog.csv`); the SKU scheme as a parser with the optional variant; `FakeConn` for tests. 87 tests. |
