"""Motion math tests — hermetic, no browser. Invariants only."""
from facebook_camofox_client.domain_camofox.motion import human_scroll_trajectory
from facebook_camofox_client.domain_camofox.primitives import (
    RefReceipt,
    clear_trace,
    jitter_delay,
    record_ref,
    trace,
)


def test_trajectory_sums_to_distance():
    for dist in (300, -800, 2500, 9000):
        steps = human_scroll_trajectory(dist, seed=11)
        assert steps
        assert abs(sum(s.delta_y for s in steps) - dist) < 0.01


def test_empty_distance_no_steps():
    assert human_scroll_trajectory(0) == []


def test_seeded_deterministic():
    a = human_scroll_trajectory(1200, seed=5)
    b = human_scroll_trajectory(1200, seed=5)
    assert [(s.delta_y, s.delay_ms) for s in a] == [(s.delta_y, s.delay_ms) for s in b]


def test_delays_never_teleport():
    for dist in (50, 1200, 9000):
        for step in human_scroll_trajectory(dist, seed=3):
            assert step.delay_ms >= 12


def test_overshoot_recoil_present_on_long_scroll():
    steps = human_scroll_trajectory(6000, seed=9)
    assert any(s.delta_y < 0 for s in steps)  # recoil opposes a downward scroll


def test_jitter_stays_in_band():
    import random

    rng = random.Random(0)
    for _ in range(50):
        assert 75.0 <= jitter_delay(100, 0.25, rng) <= 125.0


def test_ref_receipt_line_and_trace():
    clear_trace()
    ref = record_ref(RefReceipt(selector="x", x=10.0, y=20.0, width=5.0,
                                height=6.0, ok=True))
    assert "ok=1" in ref.line() and "x" in ref.line()
    assert trace() == [ref]
    clear_trace()
    assert trace() == []
