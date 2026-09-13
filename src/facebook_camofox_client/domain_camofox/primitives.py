"""Primitive enforcement flags + ref receipts.

CAMOFOX_ENFORCE_PRIMITIVES=1: instant jumps and cursor-less acts throw
instead of silently degrading (strict lifecycle for bot-telemetry safety).
Default 0: best-effort hover, fallbacks allowed (proven flows unchanged).

CAMOFOX_PRINT_REFS=1: every resolved ref prints a structured stdout line
(bounding box, coordinates, timestamps) and appends to the in-memory
trace for future calibration.
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from typing import Any


def enforce_primitives() -> bool:
    return os.getenv("CAMOFOX_ENFORCE_PRIMITIVES") == "1"


def print_refs() -> bool:
    return os.getenv("CAMOFOX_PRINT_REFS") == "1"


def jitter_delay(base_ms: float, spread: float = 0.25,
                 rng: random.Random | None = None) -> float:
    """Randomized timing so repeated actions never fire on a metronome."""
    source: Any = rng or random
    return max(5.0, base_ms * source.uniform(1.0 - spread, 1.0 + spread))


@dataclass
class RefReceipt:
    selector: str
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    resolved_at: float = field(default_factory=time.time)
    acted_at: float = 0.0
    ok: bool = False

    def line(self) -> str:
        return (f"[ref] ok={int(self.ok)} sel={self.selector!r} "
                f"xy=({self.x:.0f},{self.y:.0f}) wh=({self.width:.0f}x{self.height:.0f}) "
                f"t_resolve={self.resolved_at:.3f} t_act={self.acted_at:.3f}")


_TRACE: list[RefReceipt] = []


def record_ref(ref: RefReceipt) -> RefReceipt:
    _TRACE.append(ref)
    if print_refs():
        print(ref.line(), flush=True)
    return ref


def trace() -> list[RefReceipt]:
    return list(_TRACE)


def clear_trace() -> None:
    _TRACE.clear()
