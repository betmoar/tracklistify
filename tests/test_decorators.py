"""Tests for tracklistify.utils.decorators."""

import time

from tracklistify.utils.decorators import memoize


def test_memoize_avg_dilutes_with_hits_interleaved_buggy_divisor():
    """With the buggy total_calls divisor, hits between misses drag the
    running mean toward the FIRST miss's compute time, because the
    formula multiplies the old avg by (total_calls - 1) before averaging
    in the new sample. The correct misses-only divisor yields a clean
    mean of the actual miss compute times.

    Sequence: slow miss (~10ms) → 50 hits → fast miss (~1ms).
    - Buggy:   avg = (slow * 51 + fast) / 52 ≈ slow
    - Correct: avg = (slow + fast) / 2 ≈ slow / 2

    The assertion is expressed relative to the *measured* slow miss, not as
    an absolute millisecond bound. ``time.sleep`` only guarantees a lower
    bound, and on a loaded CI runner a 10ms sleep routinely lands at 15ms+
    — which drifted the correct mean past a hardcoded 8.0ms ceiling and
    made this test fail on roughly 60% of local runs. The ratio between the
    two divisors is what the test is actually about, and it holds under any
    scheduler slop.
    """

    @memoize()
    def f(n: int) -> int:
        # 10ms for n==1, 1ms for n==2
        time.sleep(0.010 if n == 1 else 0.001)
        return n

    t0 = time.perf_counter()
    f(1)  # miss, ~10ms
    slow_ms = (time.perf_counter() - t0) * 1000
    for _ in range(50):
        f(1)  # hits
    f(2)  # miss, ~1ms

    stats = f.get_stats()
    assert stats["misses"] == 2
    assert stats["hits"] == 50
    # Correct (misses-only) ≈ slow/2; buggy (total_calls) ≈ slow. Anything
    # below 75% of the slow miss can only come from the misses-only
    # divisor, however far the sleeps overshot.
    assert stats["avg_computation_time_ms"] < slow_ms * 0.75, (
        f"avg={stats['avg_computation_time_ms']}ms vs slow miss "
        f"{slow_ms}ms suggests a total_calls divisor (expected the "
        f"misses-only mean, ≈{slow_ms / 2:.1f}ms)"
    )
