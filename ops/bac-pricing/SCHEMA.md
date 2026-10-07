# BAC Pricing – Data Model

Build a CubeSat – the data model of the pricing engine: the contract between the data files, the `pricing` schema in the suite's database and the costing engine. The model is a multi-level bill of materials (MBOM) with recursive cost rollup: an assembly is composed of subassemblies and items to arbitrary depth, and cost rolls up from the leaves. This document versions the data model only; the tool's history is in `README.md`.

Software MIT; tabular data is CSV, hand-edited configuration is TOML.

## 1. Files

| File | Holds |
| :-- | :-- |
| `bac-items.csv` | The item register – one row per node (assembly, subassembly, part, service). Identity only. |
| `bac-bom.csv` | The BOM edges – one row per parent→child link, with the quantity and the labour and consumables incurred by that usage. |
| `bac-price-breaks.csv` | Vendor quantity-price breaks – one row per (item, break). Currency inherited from the item's vendor. |
| `bac-price-overrides.csv` | Manual per-item cost overrides and per-item rounding rules. |
| `bac-pricing-config.toml` | Global parameters, vendors, FX rates, discount tiers, batch disposition. |
| `bac-catalog.csv` | Optional. Shipping and customs attributes per sellable SKU for the shared catalog. |

The separation is deliberate: items are what things are, edges are how they are used and what that usage costs, price breaks are what vendors charge. It is what lets one subassembly (the EPS) be shared across several assemblies (Dev Kit, Education Kit) without duplication.

## 2. `bac-items.csv`

| Column | Type | Notes |
| :-- | :-- | :-- |
| `item_id` | string | Stable internal key, lowercase snake_case. The join key. Never reused. |
| `sku` | string | `bac-<cat>-<sub>-<name>-<versionstring>[-<variant>]` or empty (§6). Required for sellable items. |
| `name` | string | Display name. |
| `type` | enum | `assembly`, `subassembly`, `part`, `service`. Leaves are part and service. |
| `category` | string | `Hardware`, `Logistics`, … |
| `subcategory` | string | `STR`, `EPS`, `CDH`, `ICD`, `FST`, `PKG`, `SHP`, … – the cost breakdown by subsystem groups on it. |
| `vendor` | string | Vendor key (parts and services only). Must resolve to the vendor table. Empty for composed nodes. |
| `hs_code` | string | Customs classification. Optional. |
| `country_of_origin` | string | Optional. |
| `unit` | string | `pcs`, `service`, `kit`, … |
| `sellable` | bool | `true` → the node gets a price and appears in the price list. |
| `domain` | enum | `ground`, `flight`, `both`. Keeps flight and ground-only catalogue cleanly separated. |
| `notes` | string | Free text. |

## 3. `bac-bom.csv`

| Column | Type | Notes |
| :-- | :-- | :-- |
| `parent_id` | string | Item containing the child. |
| `child_id` | string | Item contained. |
| `qty_per_parent` | number | How many of `child` per one `parent`. Multiplies down the tree. |
| `assy_min` | number | Assembly labour (minutes) for this usage, per parent instance. |
| `qc_min` | number | QC labour, minutes. |
| `pack_min` | number | Packing labour, minutes. Conventionally only on the top assembly. |
| `ship_min` | number | Shipping labour, minutes. |
| `consumables_<base>` | number | Consumables in the base currency (`consumables_chf` when `base_currency = "CHF"`), per parent instance. |
| `ref` | string | Reference designator or position. Optional. |
| `notes` | string | Free text. |

Labour and consumables live on the edge, not the item, so the same shared part can carry different labour and consumables in different contexts (an M3 screw is threadlocked in the Fasteners usage but not in the Packaging usage). They are counted per parent instance and are not multiplied by `qty_per_parent` – a per-line, per-kit cost, matching the original spreadsheet's treatment.

## 4. `bac-price-breaks.csv`

| Column | Type | Notes |
| :-- | :-- | :-- |
| `item_id` | string | The part or service this price applies to. |
| `min_qty` | number | The break quantity. This price applies at this quantity and above, until the next break. |
| `unit_price` | number | Price per unit, in the vendor's currency. |
| `notes` | string | Quote reference or date. Optional. |

Break selection (the caution logic): for a required quantity `q`, pick the largest break at or below `q` – the conservative, more expensive bracket. If none exists, because `q` is below every quoted break, fall back to the smallest break above it; the item is then flagged as a fallback. This is the behaviour the spreadsheet was meant to have; see §7.

## 5. `bac-pricing-config.toml`

`vendors` (array): `key`, `name`, `currency`, `shipping`, `bank`, `duties`, `true_currency`. The three factors are multiplicative overhead on landed cost. `currency` drives FX conversion; the example data sets every vendor to `USD` to reproduce the legacy baseline, with `true_currency` recording the billing currency for a later switch.

`discount_tiers` (array): `label`, `kind` (`percentage` or `at_cost`), `value`, `units`. `at_cost` ignores `value` and prices at the rolled-up cost. Add rows for further tiers.

`regions` (array): `label`, `multiplier`, `currency`, `adjust`. The domestic market anchors the base price; every market is base × (its multiplier / the domestic multiplier), converted to its currency and rounded, with `adjust` added last in that market's currency.

`[financials]`, `[nonprofit]`, `[fx]`, `[batch]`: global scalars (base currency, margin, VAT, salary, safety factors, exchange rates as base currency per one unit, batch disposition).

`[rounding]`: global final-price rounding – `direction` (`up`, `down`, `nearest`) and `multiple`. Applies to final prices only, never to rolled-up costs. Per-item overrides live in `bac-price-overrides.csv`.

### 5.1 Overrides (`bac-price-overrides.csv`)

One row per item needing adjustment: `item_id`, `factor`, `additive_<base>`, `absolute_<base>`, `round_direction`, `round_multiple`, `notes`. All columns except `item_id` are nullable; unset is a no-op. Application order on the per-unit cost: absolute replaces, then factor multiplies, then additive shifts. The rounding columns override the global `[rounding]` rule for that item's final price.

## 6. SKU scheme

SKUs follow the Project & Tooling Guide §2.9:

```
bac-<cat>-<sub>-<name>-<versionstring>[-<variant>]
```

Every field lowercase; hyphens between fields and inside a name, which may carry dots for legibility (`1.5u`); the hardware version string `v<N>r<N>[.<N>]`; an optional store variant after it for the deliverable's options (`-b` B-stock, `-hdr` headers fitted, `-eu`). A revision is part of the version string, so two revisions are two SKUs; a different design (a board with two bacBus connectors) is a different item, never a variant. The example data: `bac-dev-kit-2u-v1r1` (Dev Kit v1), `bac-dev-eps-main-board-v2r2` (EPS v2 as a standalone spare), `bac-edu-kit-1u-v1r1` (Education Kit v1). Parts and services may carry SKUs but are not required to.

Open for the identity specification (suite concept §9): whether a board kitted with its buck or charger modules is a variant of the board or a bundle item of its own.

## 7. Migration notes (flat Dev Kit → hierarchy, 2026-06)

- The 46 flat line items became 1 assembly, 10 subassemblies, 41 parts and 5 services. Edge quantities are chosen so each leaf's effective per-kit quantity equals the original `pcs/kit`, preserving cost parity.
- Shared parts: `M3x30`, `M3 Nuts`, `M3 Washers` <!-- convention-check: allow A2 (a screw size) --> appeared in both the Fasteners and Packaging sections. They are single items referenced by both subassemblies with their respective quantities – the first use of shared nodes.
- Split boards: Battery Contact, Buck and Charger are modelled as subassemblies of bare PCB, components and SMT assembly service. The SMT services have no quote yet and are flagged as pending. The EPS Main Board and the MCU, CM5 and breadboard carriers are procured assembled and remain single parts.
- Bug found: the legacy spreadsheet reported a landed cost of 11'452.79 CHF. The corrected rollup is 12'058.69 CHF – the spreadsheet under-counted by 605.90 CHF across 10 items whose order quantity is below their only quoted price break; its fallback lookup returned blank instead of the next-higher bracket.
- Discrepancy flagged, not resolved: the fact sheet lists 2 battery contact PCBs per EPS; the BOM used 1. The migration preserves the BOM value for parity; change `qty_per_parent` on the `eps_v2 → bc_pcb` edge to correct it.
- Currency: all vendors are USD to reproduce the legacy baseline. RAJA (EUR), Accu (GBP) and the Swiss vendors (CHF) should be switched to their `true_currency` when multi-currency costing begins; this changes the totals.

## 8. Validation

`bac_pricing.engine.validate_model()` runs on every import and in the notebook: every edge resolves to an item, every vendor key resolves to the vendor table, no negative quantity or labour, the BOM is acyclic, every non-empty SKU follows §6 and every sellable item has one, every price break and override names an existing item. Leaves without a quote are not errors: the rollup reports them as pending and treats itself as a lower bound. A failing set is refused by `bac-db import` before anything is written.

## 9. Storage

Postgres is the single source of truth; the files above are the import source and the export target (`bac-db import pricing DIR`, `bac-db export pricing DIR`), never a parallel live copy. The `files` backend runs the notebook on the files directly for a checkout without a database.

| Table | Holds |
| :-- | :-- |
| `bac.items` | The shared item register (every BOM node). Owned by the shared layer in `bac-suite-db`. |
| `bac.catalog` | The shared sellable-SKU catalog: shipping dimensions, customs (HS code, legal country of origin, customs description, declared value, ECCN), origin story, GS1 barcode. Seeded from `bac-catalog.csv` on import; a column the file leaves empty keeps its stored value. |
| `pricing.bom`, `pricing.price_breaks`, `pricing.overrides` | The edges, the quantity breaks and the manual overrides, with suffix-less numeric columns; their denomination is the base currency of the params in force. The `_<base>` suffix exists only at the file boundary: import validates it, export re-applies it. |
| `pricing.params` | Versioned operational parameters: the whole config document (vendors, tiers, regions, financials, fx, rounding, batch) as one JSONB snapshot per save. The latest row is in force; history comes for free. |

Bootstrap configuration (backend, data directory, DSN) is `bac-suite-db`'s: `~/.config/bac/bac-suite.toml` and `BAC_DB_DSN` in `.env`.

## 10. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 1.4.0 | 2026-10-07 | SKU scheme replaced by the Tooling Guide's (§6), the three SKUs migrated; `bac-catalog.csv` as the catalog seed (§1, §9); the validation rules as `validate_model()` (§8, replacing the `validate.py` reference); cost-column suffixes written as `_<base>` throughout; item register wording; the tool history moved to `README.md`. |
| 1.3.0 | 2026-07-06 | Database-first storage: `bac.items`, `bac.catalog`, `pricing.bom`, `pricing.price_breaks`, `pricing.overrides`, `pricing.params` (§9). |
| 1.0.0 | 2026-06-18 | Cost columns in the hand-edited CSVs carry the base-currency suffix (`consumables_<base>`, `additive_<base>`, `absolute_<base>`); `salary_monthly` without a currency suffix. |
| 0.6.0 | 2026-06-17 | Regions split into eight markets with their own currency; `adjust` per region. |
| 0.2.0 | 2026-06-12 | `[rounding]` in the config and `bac-price-overrides.csv` (cost overrides, per-item rounding). |
| 0.1.0 | 2026-06-04 | Initial schema: edge-table MBOM, the flat Dev Kit v1 BOM migrated, per-vendor currency, discount tiers. |
