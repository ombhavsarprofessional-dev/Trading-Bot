"""
Module 2: Pivot Point Calculator (Traditional + Fibonacci)

Calculates Daily Pivot Points and checks Criteria 1 and Criteria 2:

CRITERIA 1 — TRADITIONAL PIVOT DOUBLE BOTTOM ZONE:
- P  = (High + Low + Close) / 3
- S1 = (2 * P) - High
- S2 = P - (High - Low)
- R1 = (2 * P) - Low
- R2 = P + (High - Low)
- The current price must be near S1 or S2 zone (within 0.5% of S1 or S2)
- S1 and S2 must be close together (gap between S1 and S2 < 1.5% of price)
  forming the "double line / confluence zone" at support.

CRITERIA 2 — FIBONACCI PIVOT DOUBLE BOTTOM ZONE:
- P  = (High + Low + Close) / 3
- S1 = P - 0.382 * (High - Low)
- S2 = P - 0.618 * (High - Low)
- R1 = P + 0.382 * (High - Low)
- R2 = P + 0.618 * (High - Low)
- The same price zone must ALSO be near Fibonacci S1 or S2 (within 1% tolerance)
- Both Traditional AND Fibonacci pivots align at support = strong confluence.
"""

import sys
from pathlib import Path
from typing import Dict, Any, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import (
    TRADITIONAL_PIVOT_TOLERANCE,
    S1_S2_MAX_GAP_RATIO,
    FIBONACCI_PIVOT_TOLERANCE,
)


def calculate_traditional_pivots(high: float, low: float, close: float) -> Dict[str, float]:
    """
    Computes Traditional Daily Pivot Points from High, Low, and Close.
    """
    p = (high + low + close) / 3.0
    hl_range = high - low
    s1 = (2.0 * p) - high
    s2 = p - hl_range
    r1 = (2.0 * p) - low
    r2 = p + hl_range

    return {
        "P": round(p, 4),
        "S1": round(s1, 4),
        "S2": round(s2, 4),
        "R1": round(r1, 4),
        "R2": round(r2, 4),
    }


def calculate_fibonacci_pivots(high: float, low: float, close: float) -> Dict[str, float]:
    """
    Computes Fibonacci Daily Pivot Points from High, Low, and Close.
    """
    p = (high + low + close) / 3.0
    hl_range = high - low
    s1 = p - (0.382 * hl_range)
    s2 = p - (0.618 * hl_range)
    r1 = p + (0.382 * hl_range)
    r2 = p + (0.618 * hl_range)

    return {
        "P": round(p, 4),
        "S1": round(s1, 4),
        "S2": round(s2, 4),
        "R1": round(r1, 4),
        "R2": round(r2, 4),
    }


def check_traditional_criteria(
    current_price: float,
    trad_pivots: Dict[str, float],
    tolerance: float = TRADITIONAL_PIVOT_TOLERANCE,
    max_gap_ratio: float = S1_S2_MAX_GAP_RATIO,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Validates CRITERIA 1:
    1. S1 and S2 must be close together: abs(S1 - S2) / current_price < max_gap_ratio (1.5%)
    2. Current price must be near S1 or S2 within tolerance (0.5%)
    """
    s1 = trad_pivots["S1"]
    s2 = trad_pivots["S2"]

    s1_s2_gap = abs(s1 - s2)
    s1_s2_gap_pct = (s1_s2_gap / current_price) if current_price > 0 else 1.0

    dist_s1 = abs(current_price - s1) / s1 if s1 > 0 else 1.0
    dist_s2 = abs(current_price - s2) / s2 if s2 > 0 else 1.0

    is_near_s1 = dist_s1 <= tolerance
    is_near_s2 = dist_s2 <= tolerance
    is_near_zone = is_near_s1 or is_near_s2
    is_gap_tight = s1_s2_gap_pct < max_gap_ratio

    matched = is_near_zone and is_gap_tight

    details = {
        "criteria_1_passed": matched,
        "s1_s2_gap": round(s1_s2_gap, 2),
        "s1_s2_gap_pct": round(s1_s2_gap_pct * 100, 2),
        "dist_s1_pct": round(dist_s1 * 100, 2),
        "dist_s2_pct": round(dist_s2 * 100, 2),
        "near_s1": is_near_s1,
        "near_s2": is_near_s2,
        "gap_tight": is_gap_tight,
    }
    return matched, details


def check_fibonacci_criteria(
    current_price: float,
    fib_pivots: Dict[str, float],
    tolerance: float = FIBONACCI_PIVOT_TOLERANCE,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Validates CRITERIA 2:
    The same price zone must ALSO be near Fibonacci S1 or S2 (within 1% tolerance).
    """
    s1 = fib_pivots["S1"]
    s2 = fib_pivots["S2"]

    dist_s1 = abs(current_price - s1) / s1 if s1 > 0 else 1.0
    dist_s2 = abs(current_price - s2) / s2 if s2 > 0 else 1.0

    is_near_s1 = dist_s1 <= tolerance
    is_near_s2 = dist_s2 <= tolerance
    is_near_zone = is_near_s1 or is_near_s2

    details = {
        "criteria_2_passed": is_near_zone,
        "dist_fib_s1_pct": round(dist_s1 * 100, 2),
        "dist_fib_s2_pct": round(dist_s2 * 100, 2),
        "near_fib_s1": is_near_s1,
        "near_fib_s2": is_near_s2,
    }
    return is_near_zone, details


def evaluate_pivot_confluence(
    high: float,
    low: float,
    close: float,
    current_price: float,
    trad_tol: float = TRADITIONAL_PIVOT_TOLERANCE,
    max_gap: float = S1_S2_MAX_GAP_RATIO,
    fib_tol: float = FIBONACCI_PIVOT_TOLERANCE,
) -> Dict[str, Any]:
    """
    Evaluates both Traditional and Fibonacci Daily Pivots and checks if
    both Criteria 1 and Criteria 2 pass simultaneously.
    """
    trad_pivots = calculate_traditional_pivots(high, low, close)
    fib_pivots = calculate_fibonacci_pivots(high, low, close)

    c1_passed, c1_details = check_traditional_criteria(current_price, trad_pivots, trad_tol, max_gap)
    c2_passed, c2_details = check_fibonacci_criteria(current_price, fib_pivots, fib_tol)

    both_passed = c1_passed and c2_passed

    # Find the lower of Traditional S2 and Fibonacci S2 (used for Stop Loss)
    min_s2 = min(trad_pivots["S2"], fib_pivots["S2"])

    # Calculate confluence tightness: distance between the matched support levels
    # Best case is when the closest Trad S and closest Fib S are virtually identical
    trad_dist = min(abs(current_price - trad_pivots["S1"]), abs(current_price - trad_pivots["S2"]))
    fib_dist = min(abs(current_price - fib_pivots["S1"]), abs(current_price - fib_pivots["S2"]))
    avg_support_dist_pct = ((trad_dist + fib_dist) / (2.0 * current_price)) * 100 if current_price > 0 else 100

    return {
        "confluence_passed": both_passed,
        "criteria_1_passed": c1_passed,
        "criteria_2_passed": c2_passed,
        "traditional": trad_pivots,
        "fibonacci": fib_pivots,
        "c1_details": c1_details,
        "c2_details": c2_details,
        "min_s2": min_s2,
        "avg_support_dist_pct": round(avg_support_dist_pct, 3),
    }


if __name__ == "__main__":
    print("Testing Step 2: Pivot Point Calculator...")

    # Let's test with a simulated scenario:
    # High: 1005, Low: 995, Close: 1000
    # Range = 10, P = 1000
    # Trad S1 = 2000 - 1005 = 995
    # Trad S2 = 1000 - 10 = 990
    # Trad gap = 5 (0.5% of 1000, which is < 1.5%)
    # Fib S1 = 1000 - 3.82 = 996.18
    # Fib S2 = 1000 - 6.18 = 993.82
    h, l, c = 1005.0, 995.0, 1000.0
    test_price = 995.2  # Very close to Trad S1 (995) and Fib S1 (996.18)

    result = evaluate_pivot_confluence(h, l, c, test_price)
    print("\nSimulated Test Bar: High=1005, Low=995, Close=1000, CurrentPrice=995.2")
    print(f"Traditional Pivots: {result['traditional']}")
    print(f"Fibonacci Pivots:   {result['fibonacci']}")
    print(f"Criteria 1 Passed:  {result['criteria_1_passed']} (gap: {result['c1_details']['s1_s2_gap_pct']}%)")
    print(f"Criteria 2 Passed:  {result['criteria_2_passed']} (Fib S1 dist: {result['c2_details']['dist_fib_s1_pct']}%)")
    print(f"Both Confluence Passed: {result['confluence_passed']}")
    print(f"Lower S2: {result['min_s2']}")

    assert result["criteria_1_passed"], "Criteria 1 should pass!"
    assert result["criteria_2_passed"], "Criteria 2 should pass!"
    assert result["confluence_passed"], "Confluence should pass!"
    print("\nAll Step 2 assertions passed successfully!")
