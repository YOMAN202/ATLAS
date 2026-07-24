"""Benchmark: previous weighted product-selection approach (numpy's native
rng.choice(replace=False, p=weights), which does real work across the
whole population on every call) vs. the optimized replacement-and-redraw
approach in generators/demand.py — at the actual scale used by the
calibrated validation run (5,000 products, Zipf/Pareto weights, up to 4
lines per order, ~800 orders/day).

Prints: timing for both approaches, and each approach's resulting ABC
demand-share breakdown (top 20% / middle 30% / remaining 50%) over many
simulated draws, as evidence the optimization changed performance only —
not the demand distribution it's meant to reproduce.
"""

import time
from collections import Counter

import numpy as np

from simulation.generators.demand import _weighted_indices_without_replacement

NUM_PRODUCTS = 5000
ZIPF_EXPONENT = 1.0
NUM_TRIALS = 50_000  # ~roughly two months of a full-scale day's order volume
LINES_PER_ORDER = 4  # config.max_lines_per_order (worst case for comparison)


def _make_weights(n: int, exponent: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    ranks = rng.permutation(n) + 1
    raw = 1.0 / np.power(ranks.astype(float), exponent)
    return raw / raw.sum()


def _previous_approach(rng: np.random.Generator, weights: np.ndarray, size: int) -> list[int]:
    return list(rng.choice(len(weights), size=size, replace=False, p=weights))


def _abc_shares(counts: Counter, n: int) -> tuple[float, float, float]:
    ordered = sorted((counts.get(i, 0) for i in range(n)), reverse=True)
    total = sum(ordered)
    top_20_n = max(1, round(n * 0.20))
    mid_30_n = max(1, round(n * 0.30))
    top = sum(ordered[:top_20_n])
    mid = sum(ordered[top_20_n : top_20_n + mid_30_n])
    bottom = sum(ordered[top_20_n + mid_30_n :])
    return (top / total * 100, mid / total * 100, bottom / total * 100)


def main() -> None:
    weights = _make_weights(NUM_PRODUCTS, ZIPF_EXPONENT, seed=42)

    print(
        f"Benchmarking {NUM_TRIALS} draws of size={LINES_PER_ORDER} "
        f"from {NUM_PRODUCTS} weighted products...",
        flush=True,
    )

    rng_prev = np.random.default_rng(1)
    prev_counts = Counter()
    t0 = time.perf_counter()
    for _ in range(NUM_TRIALS):
        for idx in _previous_approach(rng_prev, weights, LINES_PER_ORDER):
            prev_counts[idx] += 1
    t1 = time.perf_counter()
    print(f"Previous approach (replace=False, p=weights): {t1 - t0:.3f}s", flush=True)

    rng_new = np.random.default_rng(1)
    new_counts = Counter()
    t2 = time.perf_counter()
    for _ in range(NUM_TRIALS):
        for idx in _weighted_indices_without_replacement(rng_new, weights, LINES_PER_ORDER):
            new_counts[idx] += 1
    t3 = time.perf_counter()
    print(f"Optimized approach (replacement + redraw): {t3 - t2:.3f}s", flush=True)

    speedup = (t1 - t0) / (t3 - t2) if (t3 - t2) else float("inf")
    print(f"Speedup: {speedup:.1f}x", flush=True)

    prev_abc = _abc_shares(prev_counts, NUM_PRODUCTS)
    new_abc = _abc_shares(new_counts, NUM_PRODUCTS)
    print("\n--- ABC demand share comparison (statistical equivalence check) ---", flush=True)
    print(
        f"Previous: top20%={prev_abc[0]:.1f}%  mid30%={prev_abc[1]:.1f}%  "
        f"bottom50%={prev_abc[2]:.1f}%",
        flush=True,
    )
    print(
        f"Optimized: top20%={new_abc[0]:.1f}%  mid30%={new_abc[1]:.1f}%  "
        f"bottom50%={new_abc[2]:.1f}%",
        flush=True,
    )
    max_abc_diff = max(abs(a - b) for a, b in zip(prev_abc, new_abc, strict=True))
    print(f"Max ABC bucket difference: {max_abc_diff:.2f} percentage points", flush=True)


if __name__ == "__main__":
    main()
