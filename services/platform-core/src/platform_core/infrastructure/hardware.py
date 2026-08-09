"""MOCK hardware adapters — no real device communication exists here.

These simulate what future scale/analyzer integrations will return so the
transaction engine's capture flows are exercisable end-to-end. Real device
protocols arrive behind the same interfaces (PSP-0007 hardware profiles);
readings are deterministic per container so tests are stable.

**SEC-003 / F-01: these adapters refuse to produce a reading in production.**
FINAL-001 found that `source=mock_scale` was accepted in any environment, so a
SHA-256 of a container id became the net weight, which was then priced,
settled, paid and receipted. Nothing downstream can distinguish an invented
reading from a weighed one, so the refusal belongs here as well as in the
service: this is the last point at which a number that never came from a
device can be stopped, and it stops the number regardless of which caller
asked for it — HTTP route, offline sync replay, script, or a future module
that has not been written yet.
"""

import hashlib
from dataclasses import dataclass

from platform_core.core.errors import ForbiddenError


class MockHardwareRefused(ForbiddenError):
    """A fabricated measurement was requested where it is not permitted."""

    code = "mock_hardware_refused"
    message_key = "error.mock_hardware_refused"


def mock_hardware_allowed() -> bool:
    """Single source of truth, read at call time rather than import time so a
    test (or a running process) that changes the environment is obeyed."""
    from platform_core.core.config import get_settings

    return get_settings().mock_hardware_enabled


def _refuse_unless_allowed(device: str) -> None:
    if not mock_hardware_allowed():
        raise MockHardwareRefused(
            f"{device} cannot fabricate a measurement in this environment — "
            "capture a real reading instead"
        )


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
        _refuse_unless_allowed("mock_scale")
        return ScaleReading(
            gross_kg=_seed(f"gross:{container_identifier}", 8.0, 42.0),
            tare_kg=_seed(f"tare:{container_identifier}", 1.0, 3.0),
        )


class MockAnalyzerAdapter:
    """Simulates a milk analyzer (fat/SNF/CLR/density/temperature)."""

    def read(self, container_identifier: str) -> AnalyzerReading:
        _refuse_unless_allowed("mock_analyzer")
        return AnalyzerReading(
            fat=_seed(f"fat:{container_identifier}", 3.0, 6.5),
            snf=_seed(f"snf:{container_identifier}", 7.5, 9.5),
            clr=_seed(f"clr:{container_identifier}", 26.0, 32.0),
            density=_seed(f"density:{container_identifier}", 1.026, 1.032, 4),
            temperature_c=_seed(f"temp:{container_identifier}", 18.0, 30.0, 1),
        )


mock_scale = MockScaleAdapter()
mock_analyzer = MockAnalyzerAdapter()
