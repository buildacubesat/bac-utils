#!/usr/bin/env bash
# Unattended robustness sweep for the dual-feed cross. Resumable: rerun to continue.
set -u
cd "$(dirname "$0")/.."
OUT=runs/robustness
CFG=config/cross_2200_dual.toml
DES=designs/cross_2200_dual_v1.json
uv run bac-antenna sweep -c $CFG -p $DES --plan plans/robustness.toml --output $OUT
# hybrid imperfections: post-processing only, on the nominal case's field data
for c in hyb_86 hyb_94 hyb_amp_-0.3 hyb_amp_+0.3 hyb_worst; do
  mkdir -p $OUT/$c
  ln -sfn ../nominal/simulation_port1 $OUT/$c/
  ln -sfn ../nominal/simulation_port2 $OUT/$c/
done
uv run bac-antenna sweep -c $CFG -p $DES --plan plans/hybrid.toml --output $OUT
echo "sweep complete: $OUT/sweep_summary.csv"
