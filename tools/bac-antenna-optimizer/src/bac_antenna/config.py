from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Range:
    low: float
    high: float

    def sample(self, unit_value: float) -> float:
        return self.low + unit_value * (self.high - self.low)


@dataclass(frozen=True)
class Band:
    name: str
    low_hz: float
    high_hz: float
    weight: float
    max_s11_db: float
    min_gain_dbic: float          # realized gain in the wanted hand
    max_ar_db: float
    cp_span_hz: float             # AR must hold over this width, centred in the band

    @property
    def centre_hz(self) -> float:
        return (self.low_hz + self.high_hz) / 2


@dataclass(frozen=True)
class Config:
    raw: dict
    source: Path

    @property
    def project(self) -> dict:
        return self.raw.get("project", {})

    @property
    def antenna_type(self) -> str:
        """`[antenna] type` (0.6) or the legacy `[project] topology`."""
        a = self.raw.get("antenna", {})
        if "type" in a:
            return str(a["type"])
        return str(self.raw["project"]["topology"])

    topology = antenna_type      # legacy name

    @property
    def geometry(self) -> dict:
        """The antenna type's own section. Legacy configs keep `[stack]`, `[outline]`, `[feed]`, `[cavity]` at the
        top level; both layouts are served."""
        return self.raw.get("geometry", self.raw)

    @property
    def feed_network(self) -> dict:
        """`[feed_network]` (0.6): mode single | quadrature | turnstile | custom, phase_error_deg, amplitude_error_db,
        weights. Legacy `[polarization] hybrid_*` keys are mapped."""
        fn = dict(self.raw.get("feed_network", {}))
        pol = self.raw.get("polarization", {})
        fn.setdefault("phase_error_deg", float(pol.get("hybrid_phase_deg", 90.0)) - 90.0)
        fn.setdefault("amplitude_error_db", float(pol.get("hybrid_amplitude_db", 0.0)))
        return fn

    @property
    def bands(self) -> list[Band]:
        out = []
        for b in self.raw["band"]:
            low, high = float(b["low_hz"]), float(b["high_hz"])
            out.append(Band(str(b["name"]), low, high, float(b.get("weight", 1.0)), float(b.get("max_s11_db", -10.0)),
                            float(b.get("min_gain_dbic", 0.0)), float(b.get("max_ar_db", 3.0)),
                            float(b.get("cp_span_hz", high - low))))
        return out

    @property
    def primary_band(self) -> Band:
        return max(self.bands, key=lambda b: b.weight)

    @property
    def polarization(self) -> dict:
        return self.raw["polarization"]

    @property
    def stack(self) -> dict:
        return self.geometry["stack"]

    @property
    def outline(self) -> dict:
        return self.geometry["outline"]

    @property
    def feed(self) -> dict:
        return self.geometry["feed"]

    @property
    def search(self) -> dict[str, Range]:
        return {name: Range(float(v[0]), float(v[1])) for name, v in self.raw["search"].items()}

    @property
    def fixed(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.raw.get("fixed", {}).items()}

    @property
    def optimizer(self) -> dict:
        return self.raw["optimizer"]

    @property
    def mesh(self) -> dict:
        return self.raw["mesh"]

    @property
    def weights(self) -> dict:
        return self.raw["weights"]

    @property
    def cavity(self) -> dict:
        return self.geometry.get("cavity", self.raw.get("cavity", {}))

    def stack_height_mm(self) -> float:
        s = self.stack
        return float(s["gap_mm"]) + float(s["top_board_mm"]) + float(s["ground_board_mm"])

    def patch_height_mm(self) -> float:
        """Ground copper to patch copper."""
        return float(self.stack["gap_mm"]) + float(self.stack["top_board_mm"])

    def epsilon_eq(self) -> float:
        """Series-capacitor equivalent permittivity of gap + top board."""
        s = self.stack
        gap, top = float(s["gap_mm"]), float(s["top_board_mm"])
        return (gap + top) / (gap / float(s["gap_epsilon_r"]) + top / float(s["top_board_epsilon_r"]))

    def loss_tangent_eq(self) -> float:
        s = self.stack
        gap, top = float(s["gap_mm"]), float(s["top_board_mm"])
        eg, et = float(s["gap_epsilon_r"]), float(s["top_board_epsilon_r"])
        # electric energy split by layer for a uniform D field
        wg, wt = gap / eg, top / et
        return (wg * float(s["gap_loss_tangent"]) + wt * float(s["top_board_loss_tangent"])) / (wg + wt)


LEGACY_GEOMETRY_SECTIONS = ("stack", "outline", "feed", "cavity")


def apply_overrides(raw: dict, overrides: list[str]) -> dict:
    """`section.key=value` with a TOML value; bare words are taken as strings.
    Array-of-tables entries are addressed by name, e.g. band.tx.cp_span_hz=10e6. On a config with a `[geometry]`
    section the legacy prefixes `stack.`, `outline.`, `feed.`, `cavity.` are routed into it, so old plan files
    keep working."""
    for item in overrides:
        path, _, value = item.partition("=")
        keys = path.strip().split(".")
        if len(keys) < 2 or not value:
            raise ValueError(f"override {item!r} must look like section.key=value")
        if "geometry" in raw and keys[0] in LEGACY_GEOMETRY_SECTIONS:
            keys = ["geometry", *keys]
        try:
            parsed = tomllib.loads(f"v = {value}")["v"]
        except tomllib.TOMLDecodeError:
            parsed = value
        node = raw
        for k in keys[:-1]:
            if isinstance(node, list):
                match = [e for e in node if str(e.get("name")) == k]
                if not match:
                    raise ValueError(f"override {item!r}: no entry named {k!r}")
                node = match[0]
            else:
                node = node.setdefault(k, {})
        node[keys[-1]] = parsed
    return raw


def load_config(path: str | Path, overrides: list[str] | None = None) -> Config:
    source = Path(path).resolve()
    with source.open("rb") as handle:
        raw = tomllib.load(handle)
    raw = apply_overrides(raw, overrides or [])
    config = Config(raw=raw, source=source)
    validate(config)
    return config


def validate(config: Config) -> None:
    required = {"band", "polarization", "search", "optimizer", "mesh", "weights"}
    missing = sorted(required - config.raw.keys())
    if missing:
        raise ValueError(f"Missing TOML sections: {', '.join(missing)}")
    if "antenna" not in config.raw and "project" not in config.raw:
        raise ValueError("Missing [antenna] type (or legacy [project] topology)")
    from .antennas import get_antenna

    antenna = get_antenna(config)
    problems = antenna.validate_config(config)
    if problems:
        raise ValueError("; ".join(problems))
    for b in config.bands:
        if not b.low_hz < b.high_hz:
            raise ValueError(f"band {b.name}: low_hz must be below high_hz")
        if b.cp_span_hz > b.high_hz - b.low_hz + 1:
            raise ValueError(f"band {b.name}: cp_span_hz exceeds the band")
    if config.polarization["hand"].lower() not in {"rhcp", "lhcp"}:
        raise ValueError("polarization.hand must be rhcp or lhcp")
    for name, bounds in config.search.items():
        if bounds.low >= bounds.high:
            raise ValueError(f"Search range {name!r} must be [low, high] with low < high")
