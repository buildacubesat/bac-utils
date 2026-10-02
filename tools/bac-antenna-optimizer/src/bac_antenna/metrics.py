# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class BandMetrics:
    s11_worst_db: float
    gain_min_dbic: float  # realized gain in the wanted hand, worst over the band
    ar_worst_db: float  # worst over the band's cp span
    efficiency_percent: float  # radiation efficiency at band centre
    hand: str  # rhcp | lhcp | linear | unverified, at band centre


@dataclass(frozen=True)
class Metrics:
    bands: dict[str, BandMetrics]
    resonance_hz: float  # S11 minimum over the whole sweep
    modes: tuple[dict, ...] = field(default_factory=tuple)
    backend_note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)
