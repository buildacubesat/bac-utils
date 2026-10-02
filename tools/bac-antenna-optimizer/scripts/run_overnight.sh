#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Everything queued for one unattended session: freeze sweep, then the beam-width comparison.
set -u
cd "$(dirname "$0")/.."
scripts/run_freeze.sh
scripts/run_beamwidth.sh
