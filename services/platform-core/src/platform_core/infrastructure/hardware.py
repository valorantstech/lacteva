"""MOCK hardware adapters — no real device communication exists here.

These simulate what future scale/analyzer integrations will return so the
transaction engine's capture flows are exercisable end-to-end. Real device
protocols arrive behind the same interfaces (PSP-0007 hardware profiles);
readings are deterministic per container so tests are stable.
"""

import hashlib
from dataclasses import dataclass


def _seed(key: str, lo: float, hi: float, digits: int = 2) -> float:
    """Deterministic pseudo-reading in [lo, hi] derived from a key."""
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return round(lo + h * (hi - lo), digits)


@dataclass(frozen=True)
class ScaleReading:
    gross_kg: float
    tare_kg: float


@dataclass(frozen=True)
class AnalyzerReading:
    fat: float
    snf: float
    clr: float
    density: float
    temperature_c: float


class MockScaleAdapter:
    """Simulates a weighing scale (Standard/Advanced hardware profiles)."""

    def read(self, container_identifier: str) -> ScaleReading:
        return ScaleReading(
            gross_kg=_seed(f"gross:{container_identifier}", 8.0, 42.0),
            tare_kg=_seed(f"tare:{container_identifier}", 1.0, 3.0),
        )


class MockAnalyzerAdapter:
    """Simulates a milk analyzer (fat/SNF/CLR/density/temperature)."""

    def read(self, container_identifier: str) -> AnalyzerReading:
        return AnalyzerReading(
            fat=_seed(f"fat:{container_identifier}", 3.0, 6.5),
            snf=_seed(f"snf:{container_identifier}", 7.5, 9.5),
            clr=_seed(f"clr:{container_identifier}", 26.0, 32.0),
            density=_seed(f"density:{container_identifier}", 1.026, 1.032, 4),
            temperature_c=_seed(f"temp:{container_identifier}", 18.0, 30.0, 1),
        )


mock_scale = MockScaleAdapter()
mock_analyzer = MockAnalyzerAdapter()
