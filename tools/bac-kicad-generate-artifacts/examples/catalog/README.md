# Example part catalogs

A dozen rows in the shape of the Build a CubeSat catalogs (`bac-hardware/resources/`): `passives/` with one row per value, package and grade, and `ics/` with the reference part of a slot and its flight candidate. Enough to see what the `bom` stage writes; the tests use these files.

```toml
[catalog]
passives = "~/bac/bac-utils/tools/bac-kicad-generate-artifacts/examples/catalog/passives"
ics = "~/bac/bac-utils/tools/bac-kicad-generate-artifacts/examples/catalog/ics"
```

The columns the stage reads: `grade`, `value`, `package`, `role`, `status`, `manufacturer`, `mpn`, `lcsc`, `digikey`, `notes`, `tolerance`, `power_w` or `voltage_v`, `dielectric`, `height_max_mm` of a passive; `slot`, `role`, `compat`, `qualification`, `lifecycle`, `verified`, `temp_min_c`, `temp_max_c`, `manufacturer`, `mpn`, `lcsc`, `digikey`, `difference` of an IC. The other columns are kept in the files because the real catalogs carry them.

## Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 1 | 2026-10-28 | Rows taken from the Build a CubeSat catalogs (passives 0.2.0, ICs 0.3.0 of 2026-10-10), with bac-kicad-generate-artifacts 0.7.0. |
