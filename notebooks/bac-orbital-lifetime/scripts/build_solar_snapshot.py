# SPDX-License-Identifier: MIT
# /// script
# requires-python = ">=3.11"
# dependencies = ["spaceweather>=0.4", "pandas>=2.0", "numpy>=2.0"]
# ///
"""Refresh the solar-activity snapshot embedded in bac_orbital_lifetime.py.

Two sources, both public:
  - CelesTrak SW-All.csv (via the spaceweather package): daily observed
    F10.7 and Ap from 1957-10 to the present. Monthly means are written.
  - NOAA SWPC predicted-solar-cycle.json: the monthly Cycle 25 prediction
    with its 75% band. Fetched live, or read from --noaa-file (the format of
    scripts/noaa_predicted_f107_YYYY-MM-DD.txt) when the network is closed.

Prints the SOLAR_SNAPSHOT block; paste it over the block in the notebook.

Usage:
  uv run scripts/build_solar_snapshot.py --update
  uv run scripts/build_solar_snapshot.py --noaa-file scripts/noaa_predicted_f107_2026-09-17.txt
"""

import argparse
import datetime as dt
import json
import urllib.request

import spaceweather as sw

NOAA_URL = "https://services.swpc.noaa.gov/json/solar-cycle/predicted-solar-cycle.json"


def history(update):
    df = sw.sw_daily(update=update)
    obs = df[df["Apavg"] >= 0]
    m = obs[["f107_obs", "Apavg"]].resample("MS").mean()
    return m


def noaa_prediction(path):
    if path:
        rows = [line.split() for line in open(path) if line.strip() and not line.startswith("#")]
        return [(r[0], *map(float, r[1:6])) for r in rows]
    with urllib.request.urlopen(NOAA_URL, timeout=20) as f:
        data = json.load(f)
    return [
        (d["time-tag"], d["predicted_f10.7"], d["high_f10.7"], d["low_f10.7"], d["high75_f10.7"], d["low75_f10.7"])
        for d in data
    ]


def main():
    p = argparse.ArgumentParser(description="Refresh the notebook's solar snapshot.")
    p.add_argument("--update", action="store_true", help="download fresh CelesTrak data")
    p.add_argument("--noaa-file", help="read the NOAA prediction from a text file")
    a = p.parse_args()
    m = history(a.update)
    pred = noaa_prediction(a.noaa_file)
    today = dt.date.today().isoformat()
    print(f'SOLAR_SNAPSHOT_DATE = "{today}"')
    print(f'SOLAR_HISTORY_START = "{m.index[0]:%Y-%m}"')
    print(f'SOLAR_HISTORY_END = "{m.index[-1]:%Y-%m}"')
    print('SOLAR_HISTORY_F107 = """' + " ".join(f"{v:.0f}" for v in m["f107_obs"]) + '"""')
    print('SOLAR_HISTORY_AP = """' + " ".join(f"{v:.0f}" for v in m["Apavg"]) + '"""')
    print(f'NOAA_PREDICTION_START = "{pred[0][0]}"')
    for k, name in enumerate(
        ["NOAA_F107_PREDICTED", "NOAA_F107_HIGH50", "NOAA_F107_LOW50", "NOAA_F107_HIGH75", "NOAA_F107_LOW75"], start=1
    ):
        print(f'{name} = """' + " ".join(f"{r[k]:.1f}" for r in pred) + '"""')


if __name__ == "__main__":
    main()
