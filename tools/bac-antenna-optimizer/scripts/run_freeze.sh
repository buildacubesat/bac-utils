#!/usr/bin/env bash
# Freeze sweep for the v2 design (HANDOFF §4h). Resumable: rerun to continue.
set -u
cd "$(dirname "$0")/.."
OUT=runs/freeze
uv run bac-antenna sweep -c config/cross_2200_dual_v2.toml -p designs/cross_2200_dual_v2.json \
  --plan plans/freeze.toml --output $OUT
echo "freeze sweep complete: $OUT/sweep_summary.csv"
