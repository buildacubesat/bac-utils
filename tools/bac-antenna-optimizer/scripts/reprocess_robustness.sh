#!/usr/bin/env bash
# Refresh runs/robustness from its existing field data: adds the pattern columns (gain/AR over angle,
# front-to-back, back fraction) and probe_res_hz to every finished case. No FDTD; ~5-10 s per case.
set -u
cd "$(dirname "$0")/.."
OUT=runs/robustness
CFG=config/cross_2200_dual.toml
DES=designs/cross_2200_dual_v1.json
uv run bac-antenna sweep -c $CFG -p $DES --plan plans/robustness.toml --output $OUT --reprocess
uv run bac-antenna sweep -c $CFG -p $DES --plan plans/hybrid.toml --output $OUT --reprocess
echo "reprocessed: $OUT/sweep_summary.csv"
