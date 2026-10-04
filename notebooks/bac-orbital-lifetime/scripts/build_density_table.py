# SPDX-License-Identifier: MIT
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymsis>=0.11", "numpy>=2.0"]
# ///
"""Build the orbit-averaged NRLMSIS 2.1 density table for bac_orbital_lifetime.py.

For every grid cell (altitude above the 6371 km mean radius, F10.7 = F10.7a,
Ap) the mass density is averaged along a circular orbit of the given
inclination: 36 argument-of-latitude samples, 4 RAAN values (local-time
coverage), 2 dates (equinox and solstice), with the geodetic altitude of
each sample taken against the WGS84 ellipsoid. The grid also spans five inclinations (0 to 97.5 deg; the notebook mirrors
retrograde values). Output is log10(rho) in kg/m^3, 3 decimals, as one flat
string the notebook parses at start.

Usage:
  uv run scripts/build_density_table.py > density_table.txt
  uv run scripts/build_density_table.py --inclination 51.6 --coarse
"""

import argparse
import sys

import numpy as np
import pymsis

R_MEAN = 6371.0
A_WGS = 6378.137
B_WGS = 6356.752

ALT_KM = np.concatenate([np.arange(120, 300, 10), np.arange(300, 1001, 20)])
F107 = np.array([65, 75, 90, 110, 130, 150, 175, 200, 240, 300])
AP = np.array([4, 15, 40, 100])
INC = np.array([0.0, 30.0, 51.6, 70.0, 97.5])


def ellipsoid_radius(lat_deg):
    lat = np.radians(lat_deg)
    c, s = np.cos(lat), np.sin(lat)
    return np.sqrt(((A_WGS**2 * c) ** 2 + (B_WGS**2 * s) ** 2) / ((A_WGS * c) ** 2 + (B_WGS * s) ** 2))


def orbit_samples(inc_deg, n_u=36, n_raan=4):
    """Geocentric lat/lon of samples on a circular orbit, several RAANs."""
    inc = np.radians(inc_deg)
    u = np.linspace(0, 2 * np.pi, n_u, endpoint=False)
    lats, lons = [], []
    for raan in np.linspace(0, 2 * np.pi, n_raan, endpoint=False):
        lat = np.arcsin(np.sin(inc) * np.sin(u))
        lon = raan + np.arctan2(np.cos(inc) * np.sin(u), np.cos(u))
        lats.append(np.degrees(lat))
        lons.append(np.degrees(lon) % 360 - 180)
    return np.concatenate(lats), np.concatenate(lons)


def build(inc_deg, alts, f107s, aps, dates):
    lat, lon = orbit_samples(inc_deg)
    n = len(lat)
    out = np.empty((len(alts), len(f107s), len(aps)))
    for ia, h in enumerate(alts):
        r = R_MEAN + h
        h_gd = r - ellipsoid_radius(lat)
        for jf, f in enumerate(f107s):
            for ka, ap in enumerate(aps):
                rho = []
                for d in dates:
                    res = pymsis.calculate(
                        np.full(n, d, dtype="datetime64[s]"),
                        lon,
                        lat,
                        h_gd,
                        f107s=np.full(n, float(f)),
                        f107as=np.full(n, float(f)),
                        aps=np.tile([float(ap)] * 7, (n, 1)),
                    )
                    rho.append(res[:, pymsis.Variable.MASS_DENSITY])
                out[ia, jf, ka] = np.mean(np.concatenate(rho))
        print(f"  {h:4.0f} km done", file=sys.stderr)
    return out


def main():
    p = argparse.ArgumentParser(description="Orbit-averaged NRLMSIS 2.1 density table.")
    p.add_argument("--coarse", action="store_true", help="6x fewer altitude steps")
    a = p.parse_args()
    alts = ALT_KM[::6] if a.coarse else ALT_KM
    dates = [np.datetime64("2025-03-21T00:00"), np.datetime64("2025-06-21T00:00")]
    tabs = []
    for inc in INC:
        print(f"inclination {inc}", file=sys.stderr)
        tabs.append(build(inc, alts, F107, AP, dates))
    tab = np.stack(tabs)  # (inc, alt, f107, ap)
    print("# NRLMSIS 2.1 orbit-averaged log10 density, kg/m^3; axes inc, alt, f107, ap (C order)")
    print("INC", " ".join(str(x) for x in INC))
    print("ALT", " ".join(str(int(x)) for x in alts))
    print("F107", " ".join(str(int(x)) for x in F107))
    print("AP", " ".join(str(int(x)) for x in AP))
    print("LOG10RHO", " ".join(f"{v:.3f}" for v in np.log10(tab).ravel()))


if __name__ == "__main__":
    main()
