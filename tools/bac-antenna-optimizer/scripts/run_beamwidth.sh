#!/usr/bin/env bash
# Beam-width comparison (dielectric-loaded gap) on the v2 outline. Resumable: rerun to continue.
set -u
cd "$(dirname "$0")/.."
OUT=runs/beamwidth
uv run bac-antenna sweep -c config/cross_2200_dual_v2.toml -p designs/cross_2200_dual_v2.json \
  --plan plans/beamwidth.toml --output $OUT
echo "beamwidth sweep complete: $OUT/sweep_summary.csv"
