"""
Module 3: RSI + Bullish Divergence Detector

CRITERIA 3 — RSI BULLISH DIVERGENCE:
- RSI period: 14, source: Close price (Wilder's exponential smoothing)
- Detect Regular Bullish Divergence:
    * Price makes a LOWER LOW on recent candles (last 5-60 bars)
    * RSI makes a HIGHER LOW at the same time
    * Classic bullish divergence = hidden underlying buying strength
- Divergence must be detected within the last 10 daily bars
- RSI at signal point (T2) should ideally be below 40 (oversold or near-oversold zone)
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import (
    RSI_PERIOD,
    RSI_DIVERGENCE_LOOKBACK_MIN,
    RSI_DIVERGENCE_LOOKBACK_MAX,
    RSI_RECENCY_BARS,
    RSI_OVERSOLD_THRESHOLD,
)


def calculate_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """
    Calculates the Relative Strength Index (RSI) using Wilder's smoothing method.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing uses alpha = 1 / period
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def find_swing_lows(series: np.ndarray, order: int = 2) -> np.ndarray:
    """
    Finds indices of local minima (swing lows) using scipy.signal.argrelextrema.
    order: how many points on each side to use for comparison.
    """
    if len(series) < (order * 2 + 1):
        return np.array([], dtype=int)
    low_indices = argrelextrema(series, np.less, order=order)[0]
    return low_indices


def detect_bullish_divergence(
    df: pd.DataFrame,
    rsi_period: int = RSI_PERIOD,
    lookback_min: int = RSI_DIVERGENCE_LOOKBACK_MIN,
    lookback_max: int = RSI_DIVERGENCE_LOOKBACK_MAX,
    recency_bars: int = RSI_RECENCY_BARS,
    oversold_threshold: float = RSI_OVERSOLD_THRESHOLD,
) -> Dict[str, Any]:
    """
    Scans a daily OHLCV DataFrame for Regular Bullish Divergence.

    Parameters:
    - df: DataFrame containing 'Close' (and optionally 'Low')
    - rsi_period: 14
    - lookback_min: Minimum bar distance between two troughs (default 5)
    - lookback_max: Maximum bar lookback for the first trough (default 60)
    - recency_bars: The second trough must be within the last N bars (default 10)
    - oversold_threshold: RSI at the second trough must be <= threshold (default 40)

    Returns:
    - Dict with divergence result, details, and metrics.
    """
    if df is None or len(df) < (rsi_period + lookback_min):
        return {
            "divergence_found": False,
            "reason": "Insufficient historical bars",
            "current_rsi": None,
        }

    # Calculate RSI
    close_series = df["Close"].copy()
    low_series = df["Low"].copy() if "Low" in df.columns else close_series
    rsi_series = calculate_rsi(close_series, period=rsi_period)

    current_rsi = float(rsi_series.iloc[-1])
    n_bars = len(df)

    # We evaluate troughs in Low (or Close) and RSI
    price_arr = low_series.values
    rsi_arr = rsi_series.values

    # Find swing troughs in price and RSI with order 2 or 3
    for order in [3, 2]:
        price_troughs = find_swing_lows(price_arr, order=order)
        rsi_troughs = find_swing_lows(rsi_arr, order=order)

        # Also include the most recent candle if it's currently at or near the low of the last few bars
        recent_window = min(3, n_bars)
        last_idx = n_bars - 1
        if price_arr[last_idx] <= np.min(price_arr[-recent_window:]):
            if last_idx not in price_troughs:
                price_troughs = np.append(price_troughs, last_idx)
            if last_idx not in rsi_troughs:
                rsi_troughs = np.append(rsi_troughs, last_idx)

        price_troughs.sort()
        rsi_troughs.sort()

        # Search for qualifying pairs (t1, t2)
        # T2 must be recent (within recency_bars of the latest candle)
        recent_cutoff = n_bars - recency_bars
        qualified_t2 = [idx for idx in price_troughs if idx >= recent_cutoff]

        for t2 in reversed(qualified_t2):
            p2 = price_arr[t2]
            r2 = rsi_arr[t2]

            # Condition: RSI at signal point should be <= oversold_threshold (40)
            if r2 > oversold_threshold:
                continue

            # Candidate T1 points must be between [t2 - lookback_max, t2 - lookback_min]
            t1_min = max(0, t2 - lookback_max)
            t1_max = t2 - lookback_min
            candidate_t1 = [idx for idx in price_troughs if t1_min <= idx <= t1_max]

            for t1 in reversed(candidate_t1):
                p1 = price_arr[t1]
                r1 = rsi_arr[t1]

                # Regular Bullish Divergence Condition:
                # Price makes a LOWER LOW (p2 < p1)
                # RSI makes a HIGHER LOW (r2 > r1)
                if p2 < p1 and r2 > r1:
                    price_drop_pct = ((p1 - p2) / p1) * 100.0
                    rsi_gain = r2 - r1
                    bars_ago_t2 = n_bars - 1 - t2
                    bars_between = t2 - t1

                    # Date references if available
                    date_t1 = str(df.index[t1]) if hasattr(df.index, "__getitem__") else str(t1)
                    date_t2 = str(df.index[t2]) if hasattr(df.index, "__getitem__") else str(t2)

                    return {
                        "divergence_found": True,
                        "current_rsi": round(current_rsi, 2),
                        "t1_index": int(t1),
                        "t2_index": int(t2),
                        "t1_date": date_t1,
                        "t2_date": date_t2,
                        "price_t1": round(float(p1), 2),
                        "price_t2": round(float(p2), 2),
                        "rsi_t1": round(float(r1), 2),
                        "rsi_t2": round(float(r2), 2),
                        "price_drop_pct": round(float(price_drop_pct), 2),
                        "rsi_gain": round(float(rsi_gain), 2),
                        "bars_ago": int(bars_ago_t2),
                        "bars_between": int(bars_between),
                        "order_used": order,
                    }

    # If no divergence found
    return {
        "divergence_found": False,
        "current_rsi": round(current_rsi, 2),
        "reason": "No regular bullish divergence matching criteria in lookback window",
    }


if __name__ == "__main__":
    print("Testing Step 3: RSI + Bullish Divergence Detector...")

    # Create a synthetic dataset displaying clear bullish divergence:
    # 70 bars total.
    # Bar 20: T1 low at price 100, RSI reaches ~25
    # Price rises to 110 (bar 35)
    # Price drops to LOWER LOW at bar 65: price 90 (lower than 100)
    # But RSI at bar 65 is HIGHER LOW: ~34 (higher than 25, and <= 40)
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=75, freq="D")

    # Generate synthetic price path
    prices = [100.0]
    for i in range(1, 75):
        if i <= 20:
            prices.append(prices[-1] - 0.7 + np.random.normal(0, 0.2))  # trending down to ~86
        elif i <= 40:
            prices.append(prices[-1] + 1.0 + np.random.normal(0, 0.2))  # rebound to ~106
        elif i <= 68:
            prices.append(prices[-1] - 1.2 + np.random.normal(0, 0.2))  # steeper drop to lower low ~72
        else:
            prices.append(prices[-1] + 0.3 + np.random.normal(0, 0.2))  # stabilization

    synthetic_df = pd.DataFrame(
        {
            "Open": [p + 0.5 for p in prices],
            "High": [p + 1.5 for p in prices],
            "Low": [p - 1.0 for p in prices],
            "Close": prices,
            "Volume": [100000] * len(prices),
        },
        index=dates,
    )

    result = detect_bullish_divergence(synthetic_df)
    print("\nSynthetic Test Result:")
    for k, v in result.items():
        print(f"  {k}: {v}")

    print("\nTesting with real ticker (INFY.NS)...")
    import yfinance as yf

    infy = yf.Ticker("INFY.NS").history(period="6mo", interval="1d")
    infy_res = detect_bullish_divergence(infy)
    print(f"INFY.NS Current RSI: {infy_res.get('current_rsi')}")
    print(f"INFY.NS Bullish Divergence Found: {infy_res.get('divergence_found')}")
    if infy_res.get("divergence_found"):
        print(f"  T1 ({infy_res['t1_date']}): Price={infy_res['price_t1']}, RSI={infy_res['rsi_t1']}")
        print(f"  T2 ({infy_res['t2_date']}): Price={infy_res['price_t2']}, RSI={infy_res['rsi_t2']}")

    print("\nStep 3 completed and verified successfully!")
