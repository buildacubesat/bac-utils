# SPDX-License-Identifier: MIT
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Config
from .geometry import check_model
from .metrics import BandMetrics, Metrics
from .topologies import get_topology
from .vtk import write_geometry_vtp

Params = dict[str, float]


@dataclass(frozen=True)
class Evaluation:
    index: int
    params: Params
    metrics: Metrics
    score: float
    directory: Path


class Backend(Protocol):
    name: str

    def evaluate(self, params: Params, config: Config, directory: Path) -> Metrics: ...


class MockBackend:
    """Deterministic synthetic metrics. Exercises the plumbing only."""

    name = "mock"

    def evaluate(self, params: Params, config: Config, directory: Path) -> Metrics:
        digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).digest()
        u = [b / 255 for b in digest]
        bands = {
            b.name: BandMetrics(
                -25 + 20 * u[i],
                8 * u[i + 8] - 1,
                1 + 8 * u[i + 16],
                60 + 35 * u[i + 24],
                "rhcp" if u[i + 4] > 0.3 else "lhcp",
            )
            for i, b in enumerate(config.bands)
        }
        return Metrics(
            bands, config.primary_band.centre_hz * (0.95 + 0.1 * u[31]), (), "mock backend – synthetic values"
        )


def full_params(sampled: Params, config: Config) -> Params:
    return {**config.fixed, **sampled}


def score(metrics: Metrics, config: Config) -> float:
    w = config.weights
    total = 0.0
    for band in config.bands:
        if band.weight <= 0:
            continue
        m = metrics.bands[band.name]
        match = max(0.0, m.s11_worst_db - band.max_s11_db) / 3
        gain = max(0.0, band.min_gain_dbic - m.gain_min_dbic)
        axial = max(0.0, m.ar_worst_db - band.max_ar_db)
        total += band.weight * (
            float(w["match"]) * match**2 + float(w["gain"]) * gain**2 + float(w["axial_ratio"]) * axial**2
        )
    primary = config.primary_band
    pm = metrics.bands[primary.name]
    total += (
        float(w["efficiency"])
        * (max(0.0, float(w.get("min_efficiency_percent", 70)) - pm.efficiency_percent) / 10) ** 2
    )
    if not primary.low_hz <= metrics.resonance_hz <= primary.high_hz:
        half = (primary.high_hz - primary.low_hz) / 2
        total += float(w["frequency"]) * ((metrics.resonance_hz - primary.centre_hz) / half) ** 2
    return total


def _sample(units: dict[str, float], config: Config) -> Params:
    return full_params({n: b.sample(units[n]) for n, b in config.search.items()}, config)


def _random(rng: random.Random, config: Config, topology) -> Params:
    for _ in range(20_000):
        p = _sample({n: rng.random() for n in config.search}, config)
        if topology.valid(p, config):
            return p
    raise RuntimeError("Unable to find a valid point in the configured search space")


def _mutate(parent: Params, rng: random.Random, config: Config, topology, sigma: float) -> Params:
    for _ in range(2_000):
        units = {}
        for n, b in config.search.items():
            unit = (parent[n] - b.low) / (b.high - b.low)
            units[n] = min(1.0, max(0.0, unit + rng.gauss(0, sigma)))
        p = _sample(units, config)
        if topology.valid(p, config):
            return p
    return _random(rng, config, topology)


def optimise(config: Config, backend: Backend, output: Path, runs: int | None = None) -> list[Evaluation]:
    topology = get_topology(config)
    missing = set(topology.params) - set(config.search) - set(config.fixed)
    if missing:
        raise ValueError(f"{topology.name} needs search or fixed values for: {', '.join(sorted(missing))}")
    output.mkdir(parents=True, exist_ok=True)
    run_count = int(runs or config.optimizer["runs"])
    rng = random.Random(int(config.optimizer["seed"]))
    warmup = min(run_count, max(6, run_count // 4))
    evaluations: list[Evaluation] = []

    for index in range(1, run_count + 1):
        if index <= warmup or rng.random() < float(config.optimizer["restart_probability"]):
            params = _random(rng, config, topology)
        else:
            elite = max(2, math.ceil(len(evaluations) * float(config.optimizer["elite_fraction"])))
            parent = rng.choice(sorted(evaluations, key=lambda e: e.score)[:elite]).params
            progress = (index - warmup) / max(1, run_count - warmup)
            sigma = (
                float(config.optimizer["sigma_start"]) * (1 - progress)
                + float(config.optimizer["sigma_end"]) * progress
            )
            params = _mutate(parent, rng, config, topology, sigma)

        run_dir = output / f"candidate_{index:04d}"
        run_dir.mkdir(exist_ok=True)
        (run_dir / "parameters.json").write_text(json.dumps(params, indent=2) + "\n")
        model = topology.model(params, config)
        problems = check_model(model)
        if problems:
            raise RuntimeError(f"candidate {index}: " + "; ".join(problems))
        write_geometry_vtp(run_dir / "geometry.vtp", model)
        metrics = backend.evaluate(params, config, run_dir)
        s = score(metrics, config)
        (run_dir / "result.json").write_text(
            json.dumps({"score": s, "backend": backend.name, "metrics": metrics.as_dict()}, indent=2) + "\n"
        )
        evaluations.append(Evaluation(index, params, metrics, s, run_dir))
        pm = metrics.bands[config.primary_band.name]
        print(
            f"{index:04d}/{run_count:04d} score={s:8.3f} f_res={metrics.resonance_hz / 1e9:6.3f} GHz "
            f"{config.primary_band.name}: S11<={pm.s11_worst_db:6.1f} dB G>={pm.gain_min_dbic:5.1f} dBic "
            f"AR<={pm.ar_worst_db:5.1f} dB {pm.hand}"
        )

    ranked = sorted(evaluations, key=lambda e: e.score)
    _write_summary(output, ranked, config)
    _write_best(output, ranked, config, backend.name)
    return ranked


def _write_summary(output: Path, ranked: list[Evaluation], config: Config) -> None:
    band_cols = [
        f"{b.name}_{k}"
        for b in config.bands
        for k in ("s11_worst_db", "gain_min_dbic", "ar_worst_db", "efficiency_percent", "hand")
    ]
    params = sorted(ranked[0].params) if ranked else []
    with (output / "summary.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "index", "score", "resonance_hz", *params, *band_cols])
        for rank, e in enumerate(ranked, start=1):
            row = [
                rank,
                e.index,
                f"{e.score:.6f}",
                f"{e.metrics.resonance_hz:.6e}",
                *(f"{e.params[p]:.4f}" for p in params),
            ]
            for b in config.bands:
                m = e.metrics.bands[b.name]
                row += [
                    f"{m.s11_worst_db:.2f}",
                    f"{m.gain_min_dbic:.2f}",
                    f"{m.ar_worst_db:.2f}",
                    f"{m.efficiency_percent:.1f}",
                    m.hand,
                ]
            w.writerow(row)


def _write_best(output: Path, ranked: list[Evaluation], config: Config, backend: str) -> None:
    top = ranked[: int(config.optimizer.get("keep_top", 8))]
    lines = [f"# Best candidates – {config.project.get('name', config.antenna_type)}", "", f"Backend: `{backend}`", ""]
    if backend == "mock":
        lines += ["> Mock values are synthetic and must not be used for anything but software tests.", ""]
    elif backend == "cavity":
        lines += [
            "> Cavity-model values. Mode structure and resonances are physical estimates; confirm in openEMS before "
            "fabrication.",
            "",
        ]
    head = "| Rank | Candidate | Score | f_res (GHz) |" + "".join(
        f" {b.name} S11 / G / AR |" for b in config.bands if b.weight > 0
    )
    lines += [head, "|" + "---:|" * (4 + sum(1 for b in config.bands if b.weight > 0))]
    for rank, e in enumerate(top, start=1):
        cells = "".join(
            f" {e.metrics.bands[b.name].s11_worst_db:.1f} / {e.metrics.bands[b.name].gain_min_dbic:.1f} / "
            f"{e.metrics.bands[b.name].ar_worst_db:.1f} |"
            for b in config.bands
            if b.weight > 0
        )
        lines.append(f"| {rank} | {e.index:04d} | {e.score:.3f} | {e.metrics.resonance_hz / 1e9:.4f} |{cells}")
    (output / "best.md").write_text("\n".join(lines) + "\n")
