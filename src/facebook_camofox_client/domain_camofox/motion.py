"""Pure scroll-trajectory math: no page/DOM access, no I/O.

Bell-curve-velocity wheel deltas, ease-in/out, normalized so deltas sum
to the distance exactly. Semantics ported from reddit-camofox-client
domain_camofox/motion.py (itself a HumanJS planScroll port): short
scrolls collapse to fast flicks, long scrolls keep the full ramp, an
overshoot + recoil phase defeats endpoint detection, sparse pauses break
metronome timing. Delays never drop below 12ms.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class ScrollStep:
    """One wheel delta in a human scroll trajectory."""

    delta_y: float
    delay_ms: int


def _bell_phase(
    distance: float,
    *,
    segments_per_kpx: float = 18.0,
    segment_delay_ms: float = 32.0,
    delay_jitter: float = 0.20,
    rng: random.Random,
) -> list[ScrollStep]:
    if distance == 0:
        return []
    abs_dist = abs(distance)
    count = max(1, math.ceil(abs_dist / 1000.0 * segments_per_kpx))
    short_floor_ms, long_full_ms, long_ref_px = 12.0, segment_delay_ms, 5000.0
    if abs_dist >= long_ref_px:
        delay_base = long_full_ms
    else:
        t = math.log1p(abs_dist) / math.log1p(long_ref_px)
        delay_base = short_floor_ms + (long_full_ms - short_floor_ms) * t
    direction = 1.0 if distance > 0 else -1.0
    weights = [math.sin(((i + 0.5) / count) * math.pi) for i in range(count)]
    total = sum(weights)
    return [
        ScrollStep(
            delta_y=direction * abs(distance) * w / total,
            delay_ms=max(12, int(delay_base * rng.uniform(1.0 - delay_jitter,
                                                          1.0 + delay_jitter))),
        )
        for w in weights
    ]


def human_scroll_trajectory(distance: float, *, seed: int | None = None) -> list[ScrollStep]:
    """Bell-curve scroll plan with overshoot and recoil (sums to distance)."""
    rng = random.Random(seed)
    if not distance:
        return []
    direction = 1 if distance > 0 else -1
    abs_dist = abs(distance)
    long_ref_px = 5000.0
    if abs_dist >= long_ref_px:
        fraction = 0.03
    else:
        t = math.log1p(abs_dist) / math.log1p(long_ref_px)
        fraction = 0.25 + (0.03 - 0.25) * t
    extra = abs_dist * fraction
    forward = _bell_phase(abs_dist + extra, rng=rng)
    reverse = (_bell_phase(extra, segments_per_kpx=10.0, segment_delay_ms=20.0, rng=rng)
               if extra >= 1.0 else [])
    steps = forward + reverse
    out: list[ScrollStep] = []
    for idx, step in enumerate(steps):
        d = direction if idx < len(forward) else -direction
        out.append(ScrollStep(delta_y=step.delta_y * d, delay_ms=step.delay_ms))
        if 0 < idx < len(forward) - 1 and rng.random() < 0.08:
            out.append(ScrollStep(delta_y=0.0, delay_ms=rng.randint(100, 240)))
    return out
