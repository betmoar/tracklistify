"""Tests for tracklistify.utils.decorators."""

import time

from tracklistify.utils.decorators import memoize


def test_memoize_avg_dilutes_with_hits_interleaved_buggy_divisor():
    """With the buggy total_calls divisor, hits between misses drag the
    running mean toward the FIRST miss's compute time, because the
    formula multiplies the old avg by (total_calls - 1) before averaging
    in the new sample. The correct misses-only divisor yields a clean
    mean of the actual miss compute times.

    Sequence: slow miss (10ms) → 50 hits → fast miss (1ms).
    - Buggy:   avg = (10 * 51 + 1) / 52 ≈ 9.83ms
    - Correct: avg = (10 + 1) / 2 = 5.5ms
    """

    @memoize()
    def f(n: int) -> int:
        # 10ms for n==1, 1ms for n==2
        time.sleep(0.010 if n == 1 else 0.001)
        return n

    f(1)  # miss, ~10ms
    for _ in range(50):
        f(1)  # hits
    f(2)  # miss, ~1ms

    stats = f.get_stats()
    assert stats["misses"] == 2
    assert stats["hits"] == 50
    # The misses-only mean is ~5.5ms. The buggy total_calls mean is ~9.8ms.
    # Assert avg is below 8ms, which the buggy formula cannot reach in
    # this pattern.
    assert stats["avg_computation_time_ms"] < 8.0, (
        f"avg={stats['avg_computation_time_ms']}ms suggests total_calls "
        f"divisor (expected misses-only mean ≈5.5ms)"
    )
